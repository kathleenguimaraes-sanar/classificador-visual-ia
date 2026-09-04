# CetrusLabIA

Monorepo da aplicação para importar, organizar, processar, classificar e validar o portfólio de videoaulas Cetrus.

## Estrutura

- `src/` — frontend React/Vite/TypeScript operado pelo Lovable;
- `backend/` — API FastAPI, pipeline de mídia, interface local legada e testes;
- `render.yaml` — configuração legada de deploy do backend no Render.

## Frontend

O frontend usa `VITE_API_BASE_URL` para localizar a API. Copie `.env.example` para `.env.local` e execute:

```bash
npm install
npm run dev
```

O Vite também encaminha `/api` e `/health` para `http://127.0.0.1:8000` quando `VITE_API_BASE_URL` não estiver definido. O build de produção usa `https://cetruslabia.tech-pirata.workers.dev`, definido em `.env.production`.

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
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Depois de copiar `.env.example` para `.env`, preencha ao menos `GEMINI_API_KEY` e/ou `ANTHROPIC_API_KEY`. `ENABLE_OLLAMA=true` (padrão local) habilita a opção Ollama na interface — requer um servidor Ollama rodando em `OLLAMA_URL` (padrão `http://127.0.0.1:11434`) com o modelo visual já baixado (ex.: `ollama pull llava:7b`).

Preencha também `APP_AUTH_USERNAME`, `APP_AUTH_PASSWORD` e uma chave aleatória com pelo menos 32 caracteres em `APP_AUTH_SESSION_SECRET`. Para gerar a chave:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`CORS_ALLOWED_ORIGINS` recebe as origens exatas autorizadas a acessar a API, separadas por vírgula. Não use `*`. Depois do login, o frontend mantém o token de acesso somente em memória e o envia em `Authorization: Bearer`; ele nunca é gravado em `localStorage`.

Em produção, o frontend usa `https://cetruslabia.lovable.app` e a API usa `https://cetruslabia.tech-pirata.workers.dev`. Como são sites diferentes, a autenticação Bearer evita depender de cookies de terceiros. Recarregar a página ou reiniciar o navegador exige novo login.

O backend limita falhas de login por origem. Quando ele estiver acessível exclusivamente por um proxy ou túnel confiável, `APP_AUTH_TRUST_PROXY_HEADERS=true` permite identificar o cliente pelos cabeçalhos encaminhados. Mantenha `false` se a aplicação aceitar conexões diretas.

As únicas rotas públicas da API são `/health`, `/api/auth/login` e `/api/auth/session`. Com autenticação habilitada, logout, demais rotas, Swagger e schema OpenAPI exigem um token válido.

O logout invalida todas as sessões da aplicação imediatamente. Reiniciar o backend também exige novo login, assim como já ocorre com a sessão do JW Player.

### Migração de uma instalação existente

Antes de iniciar o backend pela nova estrutura, mova a configuração local da raiz para `backend/.env` e confirme que `APP_AUTH_ENABLED=true`. Não exponha a API enquanto usuário, senha, segredo de sessão e `CORS_ALLOWED_ORIGINS` não estiverem configurados.

O diretório de dados padrão agora é `backend/data`. Para preservar um banco existente, mova o conteúdo do antigo `data/` para `backend/data/` com o serviço parado ou defina `CETRUS_DATA_DIR` com o caminho absoluto do diretório antigo. Faça uma cópia de segurança de `portfolio.db` antes da migração.

Depois da instalação inicial, também é possível iniciar com duplo clique em `iniciar_aplicacao.bat` quando a autenticação estiver desabilitada para uso local.

Com `APP_AUTH_ENABLED=false`, abra `http://127.0.0.1:8000` para usar a interface legada. `/health` confirma que o processo está de pé. Com autenticação habilitada, a raiz não publica essa interface e `/docs` exige Bearer.

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

## Docker

Execute a partir da raiz do monorepo:

```bash
docker build -t cetruslabia-backend ./backend
docker run --rm -p 8000:8000 --env-file ./backend/.env cetruslabia-backend
```

Esse comando e somente para desenvolvimento local. O deploy na maquina Pirata e versionado no repositorio GitLab `sanardigital/pirata/infra-pirata/cluster-stacks` e executado exclusivamente pelo CI do runner `pirata-fisica`. O contrato operacional esta em `deploy/README.md`.

Os artefatos do backend ficam em `backend/`:

- `backend/Dockerfile` — instala FFmpeg, Chromium e as dependências Python;
- `backend/.dockerignore` — limita o contexto da imagem;
- `render.yaml` — Blueprint do serviço (sem segredos);
- `backend/.env.example` — referência das variáveis de ambiente.
- `deploy/README.md` — contrato para a stack versionada no `cluster-stacks`;
- `deploy/BACKUP_RESTORE.md` — requisitos de backup e restauracao do SQLite;
- `deploy/CLOUDFLARE.md` — Worker, VPC Service e rota HTTPS da API;
- `deploy/LOVABLE.md` — criacao e sincronizacao do frontend no Lovable.
