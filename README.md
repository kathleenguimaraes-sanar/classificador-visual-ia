# Portfólio de vídeos Cetrus

Aplicação FastAPI com interface web própria para importar, organizar, processar, classificar e validar o portfólio de videoaulas Cetrus. A solução evolui o protótipo original e mantém seus scripts experimentais como referência técnica.

## O que já está disponível

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

### 1. Preparar o repositório

Os artefatos de deploy já estão no projeto:

- `Dockerfile` — instala FFmpeg, o Chromium do Playwright (com `--with-deps`) e as dependências Python;
- `render.yaml` — Blueprint do serviço (sem segredos);
- `.dockerignore`.



