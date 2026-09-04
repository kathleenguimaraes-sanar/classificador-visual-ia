from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

from .categories import CATEGORIES, CATEGORY_NAMES

logger = logging.getLogger("cetrus.portfolio.ai")


class AIError(RuntimeError):
    pass


class AIResponseError(AIError):
    """
    Erro relativo à RESPOSTA da IA para um vídeo específico:
    conteúdo vazio, sem JSON, JSON inválido ou em formato
    inesperado.

    É uma subclasse de AIError (então qualquer código que já
    trata AIError genericamente continua funcionando), mas
    representa uma falha de UM vídeo, não da configuração do
    provedor. Diferente de um AIError "puro" (chave ausente,
    HTTP 4xx/5xx, timeout, modelo Ollama não instalado), este
    erro não deve pausar o lote inteiro — apenas esse vídeo
    deve ser marcado como erro, e o próximo vídeo continua.
    """

    def __init__(
        self,
        message: str,
        raw_text: str = "",
    ) -> None:

        super().__init__(message)

        # Guardado para diagnóstico (logs), limitado a um
        # tamanho seguro. Nunca contém credenciais — é apenas
        # o texto que a própria IA devolveu.
        self.raw_text = (raw_text or "")[:2000]


# Número de vezes que uma única análise tenta obter uma
# resposta em JSON válido da IA antes de desistir e marcar
# o vídeo como erro (sem afetar os demais vídeos do lote).
AI_JSON_MAX_ATTEMPTS = 3


# ==========================================================
# CONFIGURAÇÃO DE RETRY
# ==========================================================

RETRYABLE_STATUS_CODES = {
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

GEMINI_MAX_RETRIES = 5

GEMINI_RETRY_DELAYS = (
    2,
    4,
    8,
    16,
    32,
)


# ==========================================================
# OLLAMA
# ==========================================================

def validate_ollama_model(
    base_url: str,
    model: str,
) -> None:
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/api/tags",
            timeout=10,
        )

    except requests.RequestException as exc:
        raise AIError(
            "Ollama não está acessível. "
            "Inicie o Ollama ou escolha outro provedor."
        ) from exc

    payload = _checked(
        response,
        "Ollama",
    )

    installed = {
        str(
            item.get("name")
            or item.get("model")
            or ""
        )
        for item in payload.get(
            "models",
            [],
        )
    }

    aliases = {
        model,
        model if ":" in model else f"{model}:latest",
    }

    if not installed.intersection(aliases):
        raise AIError(
            f"O modelo Ollama '{model}' não está instalado. "
            f"Execute 'ollama pull {model}' ou escolha Gemini, "
            "OpenAI ou Claude."
        )


# ==========================================================
# PROMPT
# ==========================================================

def analysis_prompt(
    title: str,
    transcript: str = "",
    frame_times: list[float] | None = None,
) -> str:

    taxonomy = "\n".join(
        f"- {category.name}: "
        f"{category.definition} "
        f"Sinais: {category.signals}"
        for category in CATEGORIES
    )

    return f"""
Você classifica e resume aulas médicas Cetrus a partir de frames
distribuídos ao longo do vídeo.

Analise o conjunto completo de imagens, e não um frame isolado.

Use somente as evidências fornecidas.

Categorias permitidas:

{taxonomy}

Regras obrigatórias de classificação:

- Teórica core: professor aparece em contexto de estúdio junto
  aos slides de aula.

- Teórica apenas slide: os frames exibem somente slides;
  o professor não aparece.

- Demonstrativo: há prática ou demonstração de exame/procedimento,
  com paciente, professor, equipamento ou tela de exame em uso.

- Teórica core + demonstrativo: frames de momentos diferentes
  comprovam tanto a parte teórica com professor/slides quanto
  a demonstração prática. Só utilize esta categoria quando
  houver evidência clara dos DOIS componentes; a simples
  presença de um professor e um slide não basta.

- Não identificado: use apenas quando realmente não houver
  informação suficiente para classificar o vídeo. Você deve
  sempre tentar primeiro enquadrar o vídeo em uma das quatro
  categorias válidas (Teórica core, Teórica apenas slide,
  Demonstrativo, Teórica core + demonstrativo) usando o
  conjunto de frames como um todo. Não use "Não identificado"
  apenas por haver algum grau de incerteza.

- Não classifique como Demonstrativo apenas porque um slide
  contém uma imagem de exame; deve existir evidência de
  demonstração prática.

- No modo sem transcrição, não deduza características do áudio.

Título:

{title}

Frames amostrados nos segundos:

{frame_times or []}

Transcrição complementar:

{transcript[:50000] or '[não utilizada no modo rápido]'}

Responda SOMENTE com um objeto JSON válido.

Não utilize markdown (sem ```json, sem ``` de nenhum tipo).

Não escreva explicações, comentários ou qualquer texto antes
ou depois do JSON.

O JSON deve conter exatamente estes campos:

category
summary
confidence
professor_name

O campo "category" deve conter exatamente uma destas strings,
sem variações, abreviações ou texto livre:

{chr(10).join(f'"{name}"' for name in CATEGORY_NAMES)}

Regras obrigatórias para professor_name:

- Identifique o professor somente quando houver evidência confiável
  nos frames ou na transcrição complementar.

- Procure o nome em slides, créditos, títulos, identificação visual
  ou falas claramente atribuíveis ao professor.

- Não confunda paciente, autor, médico citado ou outra pessoa
  mencionada com o professor da aula.

- Preserve o nome completo quando estiver disponível.

- Se não houver evidência suficiente, use exatamente "Não identificado".

- Nunca invente um nome.

Regras obrigatórias do summary:

- escrever em português, em 1 a 3 frases completas e coerentes;

- concluir cada frase e cada ideia, sem interromper o texto
  por limite de caracteres;

- informar diretamente o principal conteúdo abordado no vídeo;

- destacar o tema e, quando houver evidência, o procedimento,
  a técnica ou o conceito apresentado;

- usar linguagem simples, objetiva e padronizada;

- aproveitar textos legíveis dos slides, o título e a transcrição
  complementar, quando disponível;

- não descrever a aparência dos frames, o processo de classificação
  ou a qualidade do áudio;

- não incluir interpretações complexas nem inventar assuntos ausentes.

confidence deve estar entre 0 e 1.

Não invente tópicos ausentes.
""".strip()


# ==========================================================
# VALIDAÇÃO DE RESPOSTA HTTP
# ==========================================================

def _checked(
    response: requests.Response,
    provider: str,
) -> dict:

    if response.status_code >= 400:
        raise AIError(
            f"{provider}: "
            f"{response.status_code} - "
            f"{response.text[:240]}"
        )

    try:
        return response.json()

    except ValueError as exc:
        raise AIError(
            f"{provider} devolveu uma resposta inválida."
        ) from exc


# ==========================================================
# OPENAI
# ==========================================================

def _openai_text(
    payload: dict,
) -> str:

    if payload.get("output_text"):
        return payload["output_text"]

    return "".join(
        part.get("text", "")
        for item in payload.get(
            "output",
            [],
        )
        for part in item.get(
            "content",
            [],
        )
        if part.get("type") == "output_text"
    )


# ==========================================================
# GEMINI - REQUEST COM RETRY
# ==========================================================

def _gemini_request(
    url: str,
    api_key: str,
    payload: dict,
) -> requests.Response:

    """
    Executa uma chamada ao Gemini com retry automático
    para erros temporários.

    Erros tratados com retry:
        429
        500
        502
        503
        504

    O objetivo principal é evitar que um 503 temporário
    interrompa todo o lote de vídeos.
    """

    last_response: requests.Response | None = None

    for attempt in range(
        GEMINI_MAX_RETRIES
    ):

        try:

            response = requests.post(
                url,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=240,
            )

        except requests.Timeout as exc:

            if attempt >= GEMINI_MAX_RETRIES - 1:
                raise AIError(
                    "Gemini excedeu o tempo limite após "
                    f"{GEMINI_MAX_RETRIES} tentativas."
                ) from exc

            delay = GEMINI_RETRY_DELAYS[
                min(
                    attempt,
                    len(GEMINI_RETRY_DELAYS) - 1,
                )
            ]

            time.sleep(delay)
            continue

        except requests.RequestException as exc:

            if attempt >= GEMINI_MAX_RETRIES - 1:
                raise AIError(
                    "Gemini não pôde ser acessado após "
                    f"{GEMINI_MAX_RETRIES} tentativas: {exc}"
                ) from exc

            delay = GEMINI_RETRY_DELAYS[
                min(
                    attempt,
                    len(GEMINI_RETRY_DELAYS) - 1,
                )
            ]

            time.sleep(delay)
            continue

        last_response = response

        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response

        if attempt >= GEMINI_MAX_RETRIES - 1:
            return response

        delay = GEMINI_RETRY_DELAYS[
            min(
                attempt,
                len(GEMINI_RETRY_DELAYS) - 1,
            )
        ]

        time.sleep(delay)

    if last_response is not None:
        return last_response

    raise AIError(
        "Gemini não retornou uma resposta."
    )


# ==========================================================
# ANÁLISE PRINCIPAL
# ==========================================================

def analyze_frames(
    provider: str,
    api_key: str,
    model: str,
    title: str,
    frames: list[dict],
    transcript: str = "",
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict:

    """
    Analisa os frames do vídeo utilizando o provedor selecionado.

    Provedores suportados:
        - Gemini
        - OpenAI
        - Claude / Anthropic
        - Ollama

    Quando a IA responde mas o texto não pode ser interpretado
    como o JSON esperado (AIResponseError), a chamada ao
    provedor é repetida até AI_JSON_MAX_ATTEMPTS vezes antes de
    desistir. Erros de configuração/infraestrutura (chave
    ausente, HTTP 4xx/5xx, timeout) continuam propagando
    imediatamente como AIError, sem retry aqui — cada provedor
    já trata os próprios erros retentáveis (ex.: Gemini/429-503).
    """

    if not frames:
        raise AIError(
            "Nenhum frame foi fornecido para análise."
        )

    prompt = analysis_prompt(
        title,
        transcript,
        [
            frame.get("timestamp", 0)
            for frame in frames
        ],
    )

    last_response_error: AIResponseError | None = None

    for attempt in range(
        AI_JSON_MAX_ATTEMPTS
    ):

        text = _request_provider_text(
            provider,
            api_key,
            model,
            prompt,
            frames,
            ollama_url,
        )

        try:

            return parse_result(
                text
            )

        except AIResponseError as exc:

            last_response_error = exc

            continue

    raise last_response_error


# ==========================================================
# CHAMADA AO PROVEDOR (TEXTO BRUTO)
# ==========================================================

def _request_provider_text(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    frames: list[dict],
    ollama_url: str,
) -> str:

    """
    Envia o prompt e os frames ao provedor selecionado e
    devolve o texto bruto da resposta (ainda não interpretado
    como JSON). Cada bloco de provedor é idêntico ao usado
    anteriormente em analyze_frames — apenas extraído para uma
    função própria, para permitir repetir só esta chamada
    quando a resposta não vier em JSON válido.
    """

    provider_key = str(
        provider or ""
    ).strip().casefold()

    # ==========================================================
    # OPENAI
    # ==========================================================

    if provider_key == "openai":

        if not api_key:
            raise AIError(
                "A chave da API da OpenAI não foi informada."
            )

        if not model:
            raise AIError(
                "O modelo da OpenAI não foi informado."
            )

        content = [
            {
                "type": "input_text",
                "text": prompt,
            }
        ]

        content.extend(
            {
                "type": "input_image",
                "image_url": (
                    f"data:{frame['mime_type']};base64,"
                    f"{frame['data']}"
                ),
            }
            for frame in frames
        )

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
            },
            timeout=240,
        )

        text = _openai_text(
            _checked(
                response,
                "OpenAI",
            )
        )

    # ==========================================================
    # GEMINI
    # ==========================================================

    elif provider_key == "gemini":

        if not api_key:
            raise AIError(
                "A chave da API do Gemini não foi informada."
            )

        if not model:
            raise AIError(
                "O modelo do Gemini não foi informado."
            )

        parts = [
            {
                "text": prompt,
            }
        ]

        parts.extend(
            {
                "inline_data": {
                    "mime_type": frame["mime_type"],
                    "data": frame["data"],
                }
            }
            for frame in frames
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": parts,
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
            },
        }

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{model}:generateContent"
        )

        response = _gemini_request(
            url,
            api_key,
            payload,
        )

        payload_response = _checked(
            response,
            "Gemini",
        )

        text = "".join(
            part.get("text", "")
            for candidate in payload_response.get(
                "candidates",
                [],
            )
            for part in candidate.get(
                "content",
                {},
            ).get(
                "parts",
                [],
            )
        )

        if not text:
            raise AIError(
                "Gemini não retornou conteúdo para análise."
            )

    # ==========================================================
    # CLAUDE / ANTHROPIC
    # ==========================================================

    elif provider_key in {
        "claude",
        "anthropic",
    }:

        if not api_key:
            raise AIError(
                "A chave da API do Claude não foi informada."
            )

        if not model:
            raise AIError(
                "O modelo do Claude não foi informado."
            )

        content = [
            {
                "type": "text",
                "text": prompt,
            }
        ]

        content.extend(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": frame["mime_type"],
                    "data": frame["data"],
                },
            }
            for frame in frames
        )

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 700,
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
            },
            timeout=240,
        )

        payload = _checked(
            response,
            "Claude",
        )

        text = "".join(
            part.get("text", "")
            for part in payload.get(
                "content",
                [],
            )
            if part.get("type") == "text"
        )

    # ==========================================================
    # OLLAMA
    # ==========================================================

    elif provider_key == "ollama":

        if not model:
            raise AIError(
                "O modelo do Ollama não foi informado."
            )

        ollama_timeout = max(
            60,
            int(
                os.getenv(
                    "OLLAMA_TIMEOUT_SECONDS",
                    "900",
                )
            ),
        )

        def ollama_payload(
            selected_frames: list[dict],
        ) -> dict:

            return {
                "model": model,
                "stream": False,
                "format": "json",
                "options": {
                    "num_ctx": 8192,
                    "temperature": 0,
                },
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [
                            frame["data"]
                            for frame in selected_frames
                        ],
                    }
                ],
            }

        # Modelos visuais locais ficam muito lentos
        # com muitas imagens.
        #
        # Quando houver mais de 4 frames,
        # utiliza quatro pontos distribuídos.

        if len(frames) > 4:

            indexes = [
                round(
                    i * (len(frames) - 1) / 3
                )
                for i in range(4)
            ]

            selected_frames = [
                frames[index]
                for index in indexes
            ]

        else:
            selected_frames = frames

        try:

            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/chat",
                json=ollama_payload(
                    selected_frames
                ),
                timeout=ollama_timeout,
            )

        except requests.Timeout as exc:

            raise AIError(
                f"Ollama excedeu "
                f"{ollama_timeout} segundos. "
                "Use um modelo visual menor ou escolha "
                "Gemini, OpenAI ou Claude."
            ) from exc

        # Alguns modelos visuais mantêm limite interno
        # de contexto menor que o solicitado.

        if (
            response.status_code == 400
            and "exceeds the available context size"
            in response.text
            and len(selected_frames) > 2
        ):

            reduced_frames = selected_frames[::2]

            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/chat",
                json=ollama_payload(
                    reduced_frames
                ),
                timeout=ollama_timeout,
            )

        payload = _checked(
            response,
            "Ollama",
        )

        text = payload.get(
            "message",
            {},
        ).get(
            "content",
            "",
        )

    # ==========================================================
    # PROVEDOR NÃO SUPORTADO
    # ==========================================================

    else:

        raise AIError(
            f"Provedor de IA não suportado: {provider}. "
            "Escolha Gemini, OpenAI, Claude ou Ollama."
        )

    return text


# ==========================================================
# PARSE DO RESULTADO
# ==========================================================

def parse_result(
    text: str,
) -> dict:

    """
    Converte a resposta da IA em um resultado padronizado.
    """

    if not text:
        raise AIResponseError(
            "A IA não devolveu conteúdo.",
            raw_text=text,
        )

    cleaned = text.strip()

    # Remove possíveis blocos Markdown:
    #
    # ```json
    # {...}
    # ```

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    # Primeiro tenta interpretar a resposta inteira.

    try:

        result = json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        # Caso a IA tenha colocado texto antes/depois
        # do JSON, tenta localizar o primeiro objeto.

        match = re.search(
            r"\{.*\}",
            cleaned,
            re.DOTALL,
        )

        if not match:

            raise AIResponseError(
                "A IA não devolveu JSON.",
                raw_text=cleaned,
            )

        try:

            result = json.loads(
                match.group(0)
            )

        except json.JSONDecodeError as exc:

            raise AIResponseError(
                "A IA devolveu JSON inválido.",
                raw_text=cleaned,
            ) from exc

    if not isinstance(result, dict):

        raise AIResponseError(
            "A IA devolveu um formato JSON inesperado.",
            raw_text=cleaned,
        )

    # ==========================================================
    # CATEGORIA
    # ==========================================================

    category = result.get(
        "category"
    )

    if category not in CATEGORY_NAMES:
        category = "Não identificado"

    # ==========================================================
    # RESUMO
    # ==========================================================

    summary = _normalize_summary(
        result.get("summary")
    )

    # ==========================================================
    # CONFIANÇA
    # ==========================================================

    try:

        confidence = max(
            0.0,
            min(
                1.0,
                float(
                    result.get(
                        "confidence",
                        0,
                    )
                ),
            ),
        )

    except (
        TypeError,
        ValueError,
    ):

        confidence = 0.0

    # ==========================================================
    # PROFESSOR
    # ==========================================================

    professor_name = str(
        result.get(
            "professor_name"
        ) or ""
    ).strip()

    if not professor_name:
        professor_name = "Não identificado"

    return {
        "category": category,
        "summary": summary,
        "confidence": confidence,
        "professor_name": professor_name,
    }


# ==========================================================
# NORMALIZAÇÃO DO RESUMO
# ==========================================================

def _normalize_summary(
    value: object,
) -> str:

    """
    Normaliza o resumo devolvido pela IA.
    """

    summary = " ".join(
        str(value or "").split()
    )

    if not summary:

        return (
            "Conteúdo não identificado "
            "nos frames analisados."
        )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        summary,
    )

    summary = " ".join(
        sentences[:3]
    ).strip()

    if (
        summary
        and summary[-1] not in ".!?"
    ):
        summary += "."

    return summary


# ==========================================================
# OPENAI - FUNÇÃO AUXILIAR
# ==========================================================

def analyze_with_openai(
    api_key: str,
    model: str,
    title: str,
    transcript: str,
) -> dict:

    if not api_key:
        raise AIError(
            "A chave da API da OpenAI não foi informada."
        )

    if not model:
        raise AIError(
            "O modelo da OpenAI não foi informado."
        )

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": analysis_prompt(
                title,
                transcript,
            ),
        },
        timeout=180,
    )

    if response.status_code >= 400:
        raise AIError(
            f"OpenAI: "
            f"{response.status_code} - "
            f"{response.text[:240]}"
        )

    try:

        payload = response.json()

    except ValueError as exc:

        raise AIError(
            "OpenAI devolveu uma resposta inválida."
        ) from exc

    text = _openai_text(
        payload
    )

    return parse_result(
        text
    )


# ==========================================================
# OLLAMA - FUNÇÃO AUXILIAR
# ==========================================================

def analyze_with_ollama(
    base_url: str,
    model: str,
    title: str,
    transcript: str,
) -> dict:

    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": analysis_prompt(
                title,
                transcript,
            ),
            "stream": False,
            "format": "json",
        },
        timeout=300,
    )

    if response.status_code >= 400:
        raise AIError(
            f"Ollama: "
            f"{response.status_code} - "
            f"{response.text[:240]}"
        )

    try:

        payload = response.json()

    except ValueError as exc:

        raise AIError(
            "Ollama devolveu uma resposta inválida."
        ) from exc

    return parse_result(
        payload.get(
            "response",
            "",
        )
    )


# ==========================================================
# CLASSIFICAÇÃO SEMÂNTICA (MACROTEMA / MICROTEMA / NANOTEMA)
# ==========================================================
#
# Etapa separada da geração do resumo: usa o "Resumo do
# conteúdo" já produzido por analyze_frames/parse_result como
# única evidência, sem reenviar frames nem reprocessar o vídeo.
# Reaproveita o mesmo dispatcher de provedores (_request_provider_text)
# usado pela análise visual — chamado aqui sem frames (chamada
# somente de texto), sem criar uma segunda integração de IA.

DEFAULT_TOPIC_CLASSIFICATION = {
    "macrotema": "Não identificado",
    "microtema": "Não identificado",
    "nanotema": "Não identificado",
}


def classification_prompt(
    summary: str,
) -> str:

    return f"""
Você classifica hierarquicamente aulas médicas Cetrus a partir do
Resumo do conteúdo abaixo, já gerado por outra etapa do sistema.

Use SOMENTE o resumo como evidência. Não utilize nenhuma outra
informação e não invente nada que não esteja nele.

Resumo do conteúdo:

{summary}

Identifique três níveis hierárquicos, nesta ordem de raciocínio:

1. Macrotema: a área médica ou conceitual mais ampla da aula
   (exemplos: Cardiologia, Neurologia, Dermatologia, Cirurgia,
   Ginecologia, Pediatria, Ortopedia, Vascular, Endocrinologia,
   Gastroenterologia). Não se limite a esta lista — identifique a
   área real a partir do conteúdo do resumo, e não apenas a partir
   destes exemplos.

2. Microtema: o assunto específico dentro do Macrotema (por
   exemplo, uma doença, condição, procedimento ou tema pontual,
   como "Insuficiência cardíaca").

3. Nanotema: o aspecto específico da aula sobre esse Microtema
   (exemplos: Medicamentos, Tratamento, Diagnóstico, Técnica,
   Procedimento, Exame, Anatomia, Fisiopatologia, Complicações,
   Conduta, Prevenção, Indicação, Contraindicação).

Regras obrigatórias:

- A classificação é SEMÂNTICA e considera o foco predominante da
  aula como um todo. Nunca classifique com base em uma palavra ou
  termo isolado do resumo. Exemplo: se o resumo cita "digoxina",
  mas o foco real da aula é o tratamento medicamentoso da
  insuficiência cardíaca em geral, o Nanotema correto é
  "Medicamentos", e não "Digoxina".

- Os três níveis precisam ser semanticamente coerentes entre si:
  o Microtema pertence ao Macrotema identificado, e o Nanotema é
  um aspecto do Microtema identificado. Nunca misture áreas
  diferentes entre os níveis.

- Quando o resumo não tiver informação suficiente para determinar
  um nível com segurança, use exatamente "Não identificado" nesse
  nível. Não invente uma classificação sem evidência suficiente no
  resumo. Se nem a área principal puder ser identificada, use
  "Não identificado" nos três níveis.

- Normalize a nomenclatura: use termos curtos, claros, objetivos e
  no padrão médico em português, de forma consistente. Não crie
  variações para o mesmo conceito (por exemplo, use sempre
  "Insuficiência cardíaca", nunca "ICC" ou "Insuficiência cardíaca
  congestiva"; use sempre "Medicamentos", nunca "Medicações" ou
  "Fármacos").

Responda SOMENTE com um objeto JSON válido.

Não utilize markdown (sem ```json, sem ``` de nenhum tipo).

Não escreva explicações, comentários ou qualquer texto antes ou
depois do JSON.

O JSON deve conter exatamente estes campos:

macrotema
microtema
nanotema
""".strip()


def _normalize_topic(
    value: object,
) -> str:

    text = " ".join(
        str(value or "").split()
    )

    if not text:
        return "Não identificado"

    return text[:1].upper() + text[1:]


def parse_classification_result(
    text: str,
) -> dict:

    """
    Converte a resposta da IA para a classificação
    macrotema/microtema/nanotema em um dicionário padronizado.
    Segue o mesmo padrão de tolerância de parse_result (remove
    cercas markdown, tenta extrair o primeiro objeto JSON).
    """

    if not text:
        raise AIResponseError(
            "A IA não devolveu conteúdo.",
            raw_text=text,
        )

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:

        result = json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        match = re.search(
            r"\{.*\}",
            cleaned,
            re.DOTALL,
        )

        if not match:

            raise AIResponseError(
                "A IA não devolveu JSON.",
                raw_text=cleaned,
            )

        try:

            result = json.loads(
                match.group(0)
            )

        except json.JSONDecodeError as exc:

            raise AIResponseError(
                "A IA devolveu JSON inválido.",
                raw_text=cleaned,
            ) from exc

    if not isinstance(result, dict):

        raise AIResponseError(
            "A IA devolveu um formato JSON inesperado.",
            raw_text=cleaned,
        )

    return {
        "macrotema": _normalize_topic(
            result.get("macrotema")
        ),
        "microtema": _normalize_topic(
            result.get("microtema")
        ),
        "nanotema": _normalize_topic(
            result.get("nanotema")
        ),
    }


def classify_topics(
    provider: str,
    api_key: str,
    model: str,
    summary: str,
    ollama_url: str = "http://127.0.0.1:11434",
) -> dict:

    """
    Classifica o resumo já existente em Macrotema/Microtema/
    Nanotema, reaproveitando o provedor/modelo de IA já
    configurado (mesmo dispatcher de analyze_frames, chamado
    aqui sem frames).

    Nunca levanta exceção: qualquer falha (JSON inválido, campo
    ausente, erro de API, timeout, resposta inesperada) é
    registrada no log e resulta em DEFAULT_TOPIC_CLASSIFICATION,
    para que uma falha de classificação nunca interrompa o
    processamento do vídeo.
    """

    summary = str(
        summary or ""
    ).strip()

    if not summary:
        return dict(
            DEFAULT_TOPIC_CLASSIFICATION
        )

    prompt = classification_prompt(
        summary
    )

    try:

        text = _request_provider_text(
            provider,
            api_key,
            model,
            prompt,
            [],
            ollama_url,
        )

        return parse_classification_result(
            text
        )

    except Exception as exc:

        logger.warning(
            "Falha ao classificar macrotema/microtema/nanotema "
            "| provider=%s model=%s erro=%s",
            provider,
            model,
            exc,
        )

        return dict(
            DEFAULT_TOPIC_CLASSIFICATION
        )