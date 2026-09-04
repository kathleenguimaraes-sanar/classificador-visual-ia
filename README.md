# CetrusLabIA

Monorepo da aplicação para importar, organizar, processar, classificar e validar o portfólio de videoaulas Cetrus.

## Estrutura

- `src/` — frontend React/Vite/TypeScript operado pelo Lovable;
- `backend/` — API FastAPI, pipeline de mídia, interface web legada e testes;
- `render.yaml` — configuração legada de deploy do backend no Render.

## Frontend

O frontend usa `VITE_API_BASE_URL` para localizar a API. Copie `.env.example` para `.env.local` e execute:

```bash
npm install
npm run dev
```

O Vite também encaminha `/api` e `/health` para `http://127.0.0.1:8000` quando `VITE_API_BASE_URL` não estiver definido. Em produção, configure o domínio HTTPS da API no ambiente do Lovable.

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

`CORS_ALLOWED_ORIGINS` recebe as origens exatas autorizadas a acessar a API, separadas por vírgula. Não use `*`. O frontend deve enviar as requisições com `credentials: "include"` para receber e reutilizar o cookie HttpOnly.

Em desenvolvimento HTTP, use `APP_AUTH_COOKIE_SECURE=false` e `APP_AUTH_COOKIE_SAMESITE=lax`. Em produção, use um domínio próprio compartilhado, como `cetruslabia.exemplo.com` no Lovable e `api.cetruslabia.exemplo.com` na máquina Pirata, com `APP_AUTH_COOKIE_SECURE=true` e `APP_AUTH_COOKIE_SAMESITE=lax`. Essa configuração evita depender de cookies de terceiros, bloqueados por alguns navegadores.

O backend limita falhas de login por origem. Quando ele estiver acessível exclusivamente por um proxy ou túnel confiável, `APP_AUTH_TRUST_PROXY_HEADERS=true` permite identificar o cliente pelos cabeçalhos encaminhados. Mantenha `false` se a aplicação aceitar conexões diretas.

As únicas rotas públicas da API são `/health` e `/api/auth/*`. Com autenticação habilitada, as demais rotas, o Swagger e o schema OpenAPI exigem uma sessão válida.

O logout invalida todas as sessões da aplicação imediatamente. Reiniciar o backend também exige novo login, assim como já ocorre com a sessão do JW Player.

### Migração de uma instalação existente

Antes de iniciar o backend pela nova estrutura, mova a configuração local da raiz para `backend/.env` e confirme que `APP_AUTH_ENABLED=true`. Não exponha a API enquanto usuário, senha, segredo de sessão e `CORS_ALLOWED_ORIGINS` não estiverem configurados.

O diretório de dados padrão agora é `backend/data`. Para preservar um banco existente, mova o conteúdo do antigo `data/` para `backend/data/` com o serviço parado ou defina `CETRUS_DATA_DIR` com o caminho absoluto do diretório antigo. Faça uma cópia de segurança de `portfolio.db` antes da migração.

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

## Docker

Execute a partir da raiz do monorepo:

```bash
docker build -t cetruslabia-backend ./backend
docker run --rm -p 8000:8000 --env-file ./backend/.env cetruslabia-backend
```

Os artefatos do backend ficam em `backend/`:

- `backend/Dockerfile` — instala FFmpeg, Chromium e as dependências Python;
- `backend/.dockerignore` — limita o contexto da imagem;
- `render.yaml` — Blueprint do serviço (sem segredos);
- `backend/.env.example` — referência das variáveis de ambiente.
