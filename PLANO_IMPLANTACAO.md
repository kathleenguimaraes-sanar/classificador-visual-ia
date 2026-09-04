# Plano de implantacao do CetrusLabIA

## Objetivo

Hospedar o frontend React no Lovable e executar o backend FastAPI na maquina Pirata, com HTTPS, autenticacao, dados persistentes e operacao segura.

Arquitetura pretendida:

- frontend: Lovable, em dominio proprio;
- backend: container Docker na maquina Pirata;
- comunicacao: API HTTPS com cookie de sessao `HttpOnly`;
- persistencia: volume local da maquina Pirata;
- codigo: monorepo no GitHub.

## Regra de publicacao

A branch `main` somente sera alterada no final, depois da homologacao. Desenvolvimento, push, PR e eventual hospedagem provisoria devem usar `feat/lovable-backend-split` ou outra branch de feature.

## Estado atual

- [x] Backend movido para `backend/`.
- [x] Frontend React/Vite criado na raiz.
- [x] Autenticacao, CORS e protecao de sessao implementados.
- [x] Concorrencia de importacao protegida com `run_id`.
- [x] Testes frontend e backend aprovados.
- [x] Imagem Docker construida.
- [x] Primeiro commit local criado: `0a9c2f9`.
- [x] Branch publicada no GitHub.
- [x] Pull Request draft aberto: https://github.com/kathleenguimaraes-sanar/CetrusLabIA/pull/1.
- [x] Artefatos operacionais do backend preparados em `deploy/`.
- [ ] Backend instalado na maquina Pirata.
- [ ] Frontend publicado no Lovable.
- [ ] Homologacao ponta a ponta concluida.
- [ ] Merge final na `main` autorizado.

## Macropasso 1 - Preparar o monorepo

Objetivo: deixar a nova arquitetura revisavel no GitHub sem alterar a `main`.

- [x] Organizar frontend e backend.
- [x] Remover artefatos gerados.
- [x] Revisar seguranca e migracao de dados.
- [x] Executar testes e build.
- [x] Criar commit na branch de feature.
- [x] Autenticar a conta GitHub do responsavel.
- [x] Fazer push de `feat/lovable-backend-split`.
- [x] Abrir PR para `main`, sem fazer merge.

Criterio de conclusao: branch remota e PR disponiveis para revisao, enquanto `main` permanece no commit anterior.

## Macropasso 2 - Preparar a maquina Pirata

Objetivo: garantir que a maquina consiga executar o backend continuamente e preservar dados.

Levantamento de 2026-09-04:

- Ubuntu 26.04 LTS `x86_64`, 8 CPUs, 30 GiB de RAM e 4 GiB de swap;
- Docker 29.6.2 e Compose 5.3.1, com Swarm single-node ativo;
- 88 GiB livres na particao principal;
- porta `8000` ocupada e `8106` livre no momento da inspecao;
- Cloudflare Tunnel existente executando na rede do host;
- nenhuma instalacao anterior do CetrusLabIA localizada.

Decisao atual: executar o backend por Docker Compose standalone, isolado das stacks Swarm, com bind somente em `127.0.0.1:8106`. O tunnel podera acessar essa porta pela rede do host sem conectar o CetrusLabIA as redes dos outros servicos.

- [x] Confirmar sistema operacional, acesso administrativo e arquitetura da maquina.
- [x] Confirmar Docker e Docker Compose.
- [ ] Desabilitar suspensao automatica da maquina.
- [ ] Definir diretorio permanente da aplicacao.
- [ ] Localizar o banco `portfolio.db` e demais dados existentes.
- [ ] Fazer backup antes da migracao.
- [ ] Definir volume persistente para `/app/data`.
- [ ] Criar `backend/.env` fora do Git com as configuracoes reais.
- [ ] Configurar reinicio automatico do container.
- [ ] Subir o backend usando a branch ou o commit homologado.
- [ ] Validar `/health`, logs e reinicio da maquina.

Variaveis obrigatorias para producao:

- `APP_AUTH_ENABLED=true`;
- `APP_AUTH_USERNAME`;
- `APP_AUTH_PASSWORD`;
- `APP_AUTH_SESSION_SECRET`;
- `APP_AUTH_COOKIE_SECURE=true`;
- `APP_AUTH_COOKIE_SAMESITE=lax`;
- `CORS_ALLOWED_ORIGINS`;
- `CETRUS_DATA_DIR`;
- chaves dos provedores de IA utilizados.

Segredos nunca devem ser enviados por chat ou adicionados ao Git.

Criterio de conclusao: backend responde internamente, exige autenticacao, preserva dados e volta automaticamente depois de reiniciar a maquina.

## Macropasso 3 - Publicar a API com seguranca

Objetivo: disponibilizar a API na internet sem expor diretamente a maquina Pirata.

- [ ] Definir o dominio principal da aplicacao.
- [ ] Reservar um subdominio para a API, como `api.cetruslabia.exemplo.com`.
- [ ] Escolher Cloudflare Tunnel ou reverse proxy equivalente.
- [ ] Configurar DNS e certificado HTTPS.
- [ ] Encaminhar apenas HTTPS para o backend local.
- [ ] Manter a porta `8000` fechada para acesso publico direto.
- [ ] Ativar `APP_AUTH_TRUST_PROXY_HEADERS=true` somente se todo acesso passar pelo proxy confiavel.
- [ ] Validar CORS com a origem exata do frontend.
- [ ] Validar rate limiting e logs de acesso.

Criterio de conclusao: `/health` responde por HTTPS, rotas privadas devolvem `401` sem sessao e somente o frontend autorizado recebe cabecalhos CORS.

## Macropasso 4 - Publicar o frontend no Lovable

Objetivo: disponibilizar a interface React conectada ao backend da Pirata.

- [ ] Criar ou selecionar o projeto no Lovable.
- [ ] Conectar o repositorio GitHub.
- [ ] Usar a branch de feature durante a homologacao, se o Lovable permitir.
- [ ] Configurar `VITE_API_BASE_URL` com a URL HTTPS da API.
- [ ] Publicar o frontend em dominio proprio, como `cetruslabia.exemplo.com`.
- [ ] Configurar esse dominio em `CORS_ALLOWED_ORIGINS` no backend.
- [ ] Confirmar que alteracoes do Lovable nao removem nem sobrescrevem `backend/`.

Frontend e API devem compartilhar o mesmo dominio registravel para o cookie `SameSite=Lax`. Um frontend em `*.lovable.app` chamando uma API em outro dominio nao e uma configuracao confiavel para a autenticacao de producao.

Criterio de conclusao: usuario entra pelo dominio do frontend, autentica e acessa a API sem erros de cookie ou CORS.

## Macropasso 5 - Homologar ponta a ponta

Objetivo: validar os fluxos reais antes de alterar a `main`.

- [ ] Login e logout da aplicacao.
- [ ] Expiracao e invalidacao de sessao.
- [ ] Login no JW Player.
- [ ] Troca de biblioteca JW Player.
- [ ] Importacao CSV/XLS/XLSX.
- [ ] Filtro por data de publicacao.
- [ ] Processamento sequencial do lote correto.
- [ ] Teste com dois navegadores para validar `run_id`.
- [ ] Acompanhamento de jobs e erros.
- [ ] Revisao e validacao humana.
- [ ] Exportacao CSV e XLSX.
- [ ] Layout desktop e mobile.
- [ ] Reinicio do backend sem perda do banco.
- [ ] Backup e restauracao testados.

Criterio de conclusao: todos os fluxos criticos funcionam no ambiente definitivo e nao ha perda de dados ou acesso indevido.

## Macropasso 6 - Entrada em producao

Objetivo: promover somente o que foi homologado.

- [ ] Revisar o PR e os checks finais.
- [ ] Registrar versao implantada e plano de rollback.
- [ ] Obter autorizacao explicita para merge.
- [ ] Fazer merge na `main`.
- [ ] Atualizar Lovable e maquina Pirata para o commit da `main`.
- [ ] Executar smoke test de producao.

Criterio de conclusao: `main`, Lovable e Pirata executam a mesma versao homologada.

## Macropasso 7 - Operacao continua

- [ ] Definir rotina de backup e retencao.
- [ ] Definir responsavel por monitorar `/health` e logs.
- [ ] Definir procedimento de atualizacao e rollback.
- [ ] Definir rotacao de senhas, chaves de IA e segredo de sessao.
- [ ] Monitorar espaco em disco e consumo de CPU/memoria.
- [ ] Documentar recuperacao depois de falha da maquina ou do tunel.

## Informacoes que dependem do responsavel

- conta GitHub com acesso de escrita ao repositorio;
- sistema operacional e forma de acesso a maquina Pirata;
- local atual do banco e dos arquivos persistentes;
- dominio escolhido e provedor de DNS;
- acesso ao Cloudflare ou proxy escolhido;
- projeto e conta do Lovable;
- provedores de IA que serao habilitados;
- decisao sobre uso local de Ollama.

## Itens que podem ser adiantados no codigo

Depois do macropasso 1, ainda antes de termos todos os acessos externos, podemos preparar:

- [x] arquivo Docker Compose para a maquina Pirata;
- [x] checklist de instalacao e verificacao de deploy;
- modelo de configuracao de proxy/tunel sem segredos;
- workflow de CI para testes de frontend e backend;
- [x] procedimento de backup e restauracao do SQLite;
- guia de configuracao do Lovable e das variaveis de ambiente.
