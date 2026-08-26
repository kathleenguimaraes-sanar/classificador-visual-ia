# Portfólio de vídeos Cetrus

Aplicação FastAPI com interface web própria para importar, organizar, processar, classificar e validar o portfólio de videoaulas Cetrus. A solução evolui o protótipo original e mantém seus scripts experimentais como referência técnica.

## O que já está disponível

- base inicial com 565 registros e 481 mídias únicas;
- importação incremental de `.xlsx`, `.xls` e `.csv` pela interface;
- validação automática das colunas `Vídeo`, `ID` e `JWPlayer ID`;
- deduplicação do processamento por `JWPlayer ID` sem perder os registros originais;
- consulta, busca, filtros e exportação em CSV;
- login assistido no painel JW Player com Playwright;
- sessão autenticada reutilizável, sem gravar a senha;
- captura da playlist HLS acessada pelo painel;
- amostragem rápida de frames distribuídos com FFmpeg (modo padrão);
- análise multimodal com Gemini, Claude ou Ollama (Ollama somente local);
- modo híbrido opcional com frames e transcrição Whisper;
- classificação nas categorias definidas pelo projeto;
- revisão humana do modelo de aula e do resumo;
- persistência local em SQLite.

## Executar localmente

Requer Python 3.11 ou mais recente e FFmpeg instalado (disponível no `PATH`).

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Depois de copiar `.env.example` para `.env`, preencha ao menos `GEMINI_API_KEY` e/ou `ANTHROPIC_API_KEY`. `ENABLE_OLLAMA=true` (padrão local) habilita a opção Ollama na interface — requer um servidor Ollama rodando em `OLLAMA_URL` (padrão `http://127.0.0.1:11434`) com o modelo visual já baixado (ex.: `ollama pull llava:7b`).

Depois da instalação inicial, também é possível iniciar com duplo clique em `iniciar_aplicacao.bat`.

Abra `http://127.0.0.1:8000` no navegador. `/docs` mostra a documentação interativa (Swagger) gerada pelo FastAPI, e `/health` confirma que o processo está de pé.

## Conexão com o JW Player

O fluxo começa em `https://dashboard.jwplayer.com/p/XdfUPSCL/media`. A aplicação abre um navegador Chromium controlado e mantém a sessão somente em memória, sem gravar a senha.

Depois que a sessão for confirmada, a aplicação libera a planilha e inicia automaticamente a captura, amostragem de frames, classificação e geração dos resumos dos IDs pendentes.

Ao processar uma mídia, o sistema abre sua página no painel, captura a fonte HLS/MP4 e extrai de 4 a 16 frames distribuídos ao longo da duração. O padrão é de 8 frames. A estratégia híbrida adiciona o áudio e deve ser reservada a aulas em que a evidência visual não basta.

O processamento é estritamente sequencial: o próximo vídeo só começa depois que captura, IA e gravação do resultado anterior terminam.

## CLI resiliente

```powershell
python main.py --run
python main.py --status
python main.py --retry-errors
```

A CLI persiste os estados `pending`, `downloading`, `transcribing`, `classifying`, `summarizing`, `done` e `error`. Execuções interrompidas retomam na etapa registrada e os logs JSONL ficam em `data/logs`.

Antes de usar `--run`, copie `.env.example` para `.env` e preencha o bloco `CUSTOM_SYSTEM_PROMPT` em `src/portfolio/classify.py`.

## Deploy no Render

A aplicação sobe como um único Web Service Docker: FastAPI, a fila de processamento e a sessão Playwright/Chromium do JW Player rodam no mesmo processo (não existe um "agente" separado a hospedar). Ollama fica desabilitado — é uma dependência exclusivamente local.

### 1. Preparar o repositório

Os artefatos de deploy já estão no projeto:

- `Dockerfile` — instala FFmpeg, o Chromium do Playwright (com `--with-deps`) e as dependências Python;
- `render.yaml` — Blueprint do serviço (sem segredos);
- `.dockerignore`.

### 2. Publicar no GitHub

```bash
git add .
git commit -m "chore: prepara deploy no Render"
git push
```

### 3. Criar o Web Service no Render

1. Em [render.com](https://render.com), **New > Blueprint** e conecte o repositório (o Render lê `render.yaml` automaticamente), **ou** **New > Web Service** manual com:

   ```text
   Runtime:        Docker
   Build Command:  (definido pelo Dockerfile — deixar em branco)
   Start Command:  (definido pelo Dockerfile — deixar em branco)
   Health Check:   /health
   ```

2. Adicione um **Persistent Disk** (obrigatório — sem ele, o banco SQLite e o histórico de execuções são apagados a cada deploy):

   ```text
   Mount Path: /data
   Size:       1 GB (ajuste conforme o volume de vídeos)
   ```

3. Configure as **Environment Variables** (nenhuma vem preenchida por padrão — configure manualmente em Render > Environment):

   ```text
   GEMINI_API_KEY=<sua chave>
   ANTHROPIC_API_KEY=<sua chave>
   ENABLE_OLLAMA=false
   CETRUS_DATA_DIR=/data
   ```

4. Deploy. O Render expõe uma URL como `https://portfolio-cetrus.onrender.com`.

### 4. Plano do serviço

Planos gratuitos do Render "dormem" após inatividade de requisições HTTP. Como o processamento em lote roda em uma thread de fundo (sem gerar requisições HTTP contínuas), um lote grande pode ser interrompido no meio se o serviço for suspenso. Use pelo menos o plano **Starter** para lotes reais.

### 5. Testar após o deploy

Progressivamente, não com os 565 vídeos de uma vez:

```text
GET /            → interface carrega
GET /health      → {"ok": true}
GET /docs        → documentação Swagger
GET /api/status  → {"gemini": true, "claude": true, "ollama_enabled": false, "jw_agent": false}
```

Depois: conectar ao JW Player → processar 1 vídeo com Gemini → 1 com Claude → planilha pequena (5–10 vídeos) → só então planilhas maiores, observando CPU/memória/tempo no painel do Render.

### Limitações conhecidas

- **Disco**: sem o Persistent Disk montado em `CETRUS_DATA_DIR`, todo o histórico é perdido a cada deploy/restart.
- **Fila em memória**: um restart no meio de um lote perde a fila em andamento (os vídeos já concluídos permanecem salvos; os pendentes precisam ser reenviados). Não há migração para banco/fila externos nesta versão — mantido como no protótipo original, documentado aqui como limitação conhecida em vez de resolvido silenciosamente.
- **Primeira transcrição** (modo híbrido) pode demorar mais: o modelo Whisper é baixado na primeira execução.

## Testes

```bash
python -m unittest discover -s tests -v
```

Os testes cobrem a validação da planilha, a importação idempotente e o compartilhamento de análises por `JWPlayer ID`.
