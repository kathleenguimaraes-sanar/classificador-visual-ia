# Backup e restauracao

## Escopo

O item critico e `portfolio.db`, armazenado com arquivos SQLite WAL/SHM no diretorio persistente. Backups definitivos devem sair do mesmo disco da aplicacao.

Arquivos temporarios em `data/work` podem ser descartados quando nao houver processamento em execucao. Logs podem ter retencao separada.

## Backup online do SQLite

O procedimento versionado no `cluster-stacks` deve usar a API nativa de backup do SQLite, validar a copia com `PRAGMA integrity_check` e transferi-la para um destino fora da maquina Pirata. Nao copie o arquivo ativo diretamente nem execute uma rotina improvisada no host.

## Backup frio antes da primeira migracao

1. Confirme que nao ha jobs em execucao.
2. Use o job ou procedimento versionado da stack para parar somente o backend.
3. Preserve o diretorio de dados inteiro, incluindo `portfolio.db`, `portfolio.db-wal` e `portfolio.db-shm` quando existirem.
4. Preserve proprietario, permissoes e timestamps.
5. Valide uma copia do banco com `PRAGMA integrity_check`.
6. Registre o commit ou a imagem correspondente ao backup.

Nao copie apenas `portfolio.db` enquanto o processo estiver gravando.

## Restauracao

Restaurar um backup descarta dados gravados depois dele. Obtenha autorizacao explicita e execute somente pelo procedimento versionado da stack.

1. Pare somente o backend do CetrusLabIA.
2. Copie o diretorio atual para uma area de seguranca com timestamp.
3. Restaure o backup validado como `portfolio.db`.
4. Remova arquivos `portfolio.db-wal` e `portfolio.db-shm` pertencentes ao banco substituido.
5. Confirme proprietario e permissoes do diretorio persistente.
6. Inicie o backend.
7. Confirme `/health`, `PRAGMA integrity_check`, contagem de videos, login e exportacao.
8. Registre o backup restaurado e o resultado da verificacao.

## Retencao minima sugerida

- backups diarios dos ultimos 7 dias;
- backups semanais das ultimas 4 semanas;
- um backup pre-deploy para cada versao implantada;
- pelo menos uma copia recente fora da maquina Pirata.

Monitore espaco livre e teste uma restauracao periodicamente. Um backup nunca restaurado e apenas uma expectativa de recuperacao.
