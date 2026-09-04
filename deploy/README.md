# Implantacao na maquina Pirata

Este diretorio prepara o macropasso 2 de `PLANO_IMPLANTACAO.md`. Os comandos devem ser executados somente depois de revisar os caminhos, a porta e o estado dos jobs da aplicacao.

## Ambiente confirmado

- Ubuntu 26.04 LTS `x86_64`;
- Docker Engine 29.6.2 e Docker Compose 5.3.1;
- Docker Swarm ativo em no unico, sem alteracao planejada;
- 30 GiB de RAM e 4 GiB de swap;
- 88 GiB livres na particao principal no levantamento inicial;
- porta `8000` ocupada por outro servico;
- Cloudflare Tunnel existente na rede `host`.

O CetrusLabIA sera executado por Compose standalone, isolado das stacks Swarm. A API ficara em `127.0.0.1:8106` por padrao e nao sera acessivel diretamente pela rede.

## Arquivos e caminhos

- checkout: `/srv/pirata/cetruslabia/app`;
- configuracao secreta: `/srv/pirata/cetruslabia/backend.env`;
- dados persistentes: `/srv/pirata/cetruslabia/data`;
- backups locais temporarios: `/srv/pirata/cetruslabia/backups`;
- manifest: `deploy/compose.yaml`.

O banco e seus arquivos WAL/SHM devem permanecer no mesmo volume persistente. Nao monte somente `portfolio.db`.

## Preparacao

1. Confirme que `8106` continua livre.
2. Confirme que nao ha jobs em execucao na instalacao anterior.
3. Crie os diretorios de checkout, dados e backups.
4. Copie `deploy/backend.env.example` para o caminho externo `backend.env`.
5. Preencha os segredos diretamente na Pirata e restrinja a leitura do arquivo ao administrador do deploy.
6. Se existir um banco anterior, siga `deploy/BACKUP_RESTORE.md` antes de move-lo.
7. Use o commit homologado da branch de feature; nao e necessario fazer merge na `main`.

Variaveis operacionais opcionais podem ser informadas antes de cada comando:

```bash
export CETRUS_IMAGE_TAG=358665d
export CETRUS_HOST_PORT=8106
export CETRUS_ENV_FILE=/srv/pirata/cetruslabia/backend.env
export CETRUS_DATA_HOST_DIR=/srv/pirata/cetruslabia/data
```

Use como tag o SHA efetivamente implantado. O exemplo acima deve ser atualizado quando houver novo commit homologado.

## Validacao do manifest

Execute a partir da raiz do checkout:

```bash
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml build backend
```

A construcao local pode consumir CPU, memoria e disco. Na primeira instalacao, execute em horario controlado e acompanhe os servicos existentes. Atualizacoes futuras devem preferir uma imagem ja construida e identificada por SHA.

## Inicializacao

```bash
docker compose -f deploy/compose.yaml up -d --build --wait --wait-timeout 180 backend
docker compose -f deploy/compose.yaml ps backend
docker compose -f deploy/compose.yaml logs --since=10m backend
```

Nunca execute `docker compose down -v`, `docker system prune` ou comandos globais do Swarm como parte deste deploy.

## Smoke test local

```bash
curl --fail --show-error http://127.0.0.1:8106/health
curl --output /dev/null --write-out '%{http_code}\n' http://127.0.0.1:8106/api/status
```

Resultados esperados:

- `/health`: HTTP 200 e `{"ok":true}`;
- `/api/status` sem cookie: HTTP 401;
- container: estado `healthy`;
- demais stacks e servicos: sem alteracao.

Depois do login, valide importacao, um processamento representativo e persistencia apos `docker compose restart backend`.

## Integracao futura com Cloudflare

O tunnel existente usa a rede do host. Depois de definir o dominio, adicione uma rota para `http://127.0.0.1:8106`. Nao conecte o CetrusLabIA as redes das outras stacks e nao exponha a porta em `0.0.0.0`.

Mantenha `APP_AUTH_TRUST_PROXY_HEADERS=false` ate confirmar que o acesso direto esta bloqueado e que o proxy sobrescreve os cabecalhos de IP do cliente.

## Atualizacao e rollback

1. Confirme que nao ha jobs `queued` ou `running`.
2. Gere um backup consistente do SQLite.
3. Construa ou disponibilize a nova imagem antes da janela de troca.
4. Atualize `CETRUS_IMAGE_TAG` para o novo SHA.
5. Execute `docker compose -f deploy/compose.yaml up -d --no-build --wait backend`.
6. Execute o smoke test imediatamente.
7. Em falha, volte para a tag anterior. Restaure banco somente quando necessario e com autorizacao explicita, pois isso descarta gravacoes posteriores ao backup.

Nao ha garantia de zero downtime: fila, sessao da aplicacao e login do JW Player ficam em memoria. Uma atualizacao deve ser uma parada curta e controlada, com novo login depois da reinicializacao.
