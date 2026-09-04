# Plano de implantacao do CetrusLabIA

## Objetivo

Hospedar o frontend React no Lovable e executar o backend FastAPI na maquina Pirata, com HTTPS, autenticacao, dados persistentes e operacao segura.

Arquitetura pretendida:

- frontend: Lovable em `https://cetruslabia.lovable.app`;
- backend: container Docker na maquina Pirata, publicado em `https://cetruslabia.tech-pirata.workers.dev`;
- comunicacao: API HTTPS com token Bearer mantido somente em memoria;
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
- [x] Contrato operacional do backend documentado em `deploy/`.
- [ ] Stack `cetruslabia` versionada no `cluster-stacks` e enviada para revisao.
- [ ] Backend implantado pelo CI do runner `pirata-fisica`.
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

## Macropasso 2 - Implantar o servico pela stack

Objetivo: versionar a operacao do backend no `cluster-stacks`, sem instalacao ou configuracao manual na maquina Pirata.

- [x] Confirmar Docker Swarm, capacidade e porta candidata `8106`.
- [ ] Carregar a skill `maquina-pirata` antes de qualquer operacao de infraestrutura.
- [ ] Criar a stack `cetruslabia` no repositorio `sanardigital/pirata/infra-pirata/cluster-stacks`.
- [ ] Configurar persistencia para `/app/data`, healthcheck e restart policy.
- [ ] Mapear credenciais do 1Password em `secrets.map` e Docker Secrets.
- [ ] Abrir MR e aguardar o CI verde.
- [ ] Enviar o MR e o nome da stack ao Pedro Mascarenhas para revisao.
- [ ] Fazer merge somente depois da aprovacao.
- [ ] Deixar o runner `pirata-fisica` realizar o deploy e a verificacao.
- [ ] Validar `/health`, logs, backup, persistencia e restart.

Hermes nao participa deste deploy porque o CetrusLabIA nao e um servico de agente.

Variaveis obrigatorias para producao:

- `APP_AUTH_ENABLED=true`;
- `APP_AUTH_USERNAME`;
- `APP_AUTH_PASSWORD`;
- `APP_AUTH_SESSION_SECRET`;
- `CORS_ALLOWED_ORIGINS`;
- `CETRUS_DATA_DIR`;
- chaves dos provedores de IA utilizados.

Segredos devem sair do 1Password diretamente para Docker Secrets. Seus valores nunca devem passar por chat, Git, CI ou arquivo.

Criterio de conclusao: backend responde internamente, exige autenticacao, preserva dados e volta automaticamente depois de reiniciar a maquina.

## Macropasso 3 - Publicar a API com seguranca

Objetivo: disponibilizar a API na internet sem expor diretamente a maquina Pirata.

- [x] Definir a URL da API: `cetruslabia.tech-pirata.workers.dev`.
- [ ] Depois de validar a stack, adicionar `cetruslabia:8106` ao estado desejado de `tunnel/cloudflare/reconcile.sh` em uma alteracao separada.
- [ ] Criar Worker e binding de VPC Service pelo fluxo do `cluster-stacks`.
- [x] Escolher o Cloudflare Tunnel existente `piratas-fisica`.
- [x] Proibir quick tunnel e acesso do Worker a `<uuid>.cfargotunnel.com`.
- [ ] Configurar DNS e certificado HTTPS.
- [ ] Encaminhar apenas HTTPS para o backend local.
- [ ] Manter a porta `8000` fechada para acesso publico direto.
- [ ] Ativar `APP_AUTH_TRUST_PROXY_HEADERS=true` somente se todo acesso passar pelo proxy confiavel.
- [ ] Validar CORS com a origem exata do frontend.
- [ ] Validar rate limiting e logs de acesso.
- [ ] Confirmar que trabalhos longos usam jobs assincronos e nao dependem de uma requisicao aberta no edge.

Criterio de conclusao: `/health` responde por HTTPS, rotas privadas devolvem `401` sem sessao e somente o frontend autorizado recebe cabecalhos CORS.

## Macropasso 4 - Publicar o frontend no Lovable

Objetivo: disponibilizar a interface React conectada ao backend da Pirata.

Este macropasso comeca somente depois de o backend estar implantado e saudavel.

- [ ] Criar ou selecionar o projeto no Lovable.
- [ ] Conectar o repositorio GitHub.
- [ ] Usar a branch de feature durante a homologacao, se o Lovable permitir.
- [x] Configurar `VITE_API_BASE_URL=https://cetruslabia.tech-pirata.workers.dev` para producao.
- [ ] Publicar o frontend em `cetruslabia.lovable.app`.
- [ ] Configurar esse dominio em `CORS_ALLOWED_ORIGINS` no backend.
- [ ] Confirmar que alteracoes do Lovable nao removem nem sobrescrevem `backend/`.

Frontend e API usam dominios registraveis diferentes. Por isso, a autenticacao usa token Bearer somente em memoria e nao depende de cookies de terceiros. Recarregar a pagina exige novo login.

Criterio de conclusao: usuario entra pelo frontend, autentica e acessa a API com Bearer sem erros de CORS.

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
- acesso ao estado desejado Cloudflare do tunnel `piratas-fisica`;
- acesso ao Cloudflare ou proxy escolhido;
- projeto e conta do Lovable;
- provedores de IA que serao habilitados;
- decisao sobre uso local de Ollama.

## Itens que podem ser adiantados no codigo

Depois do macropasso 1, ainda antes de termos todos os acessos externos, podemos preparar:

- [x] contrato da stack para o repositorio `cluster-stacks`;
- [x] checklist de deploy e verificacao pelo CI;
- [x] modelo de configuracao do Worker/VPC Service sem segredos;
- workflow de CI para testes de frontend e backend;
- [x] procedimento de backup e restauracao do SQLite;
- guia de configuracao do Lovable e das variaveis de ambiente.
