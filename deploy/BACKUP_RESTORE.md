# Backup e restauracao

## Escopo

O item critico e `portfolio.db`, armazenado com arquivos SQLite WAL/SHM no diretorio persistente. Backups definitivos devem sair do mesmo disco da aplicacao.

Arquivos temporarios em `data/work` podem ser descartados quando nao houver processamento em execucao. Logs podem ter retencao separada.

## Backup online do SQLite

O backup online usa a API nativa do SQLite e evita copiar um banco ativo de forma inconsistente. Execute a partir da raiz do checkout:

```bash
docker compose -f deploy/compose.yaml exec -T backend python -c "from datetime import datetime, timezone; from pathlib import Path; import sqlite3; stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); target=Path('/app/data/backups') / f'portfolio-{stamp}.db'; target.parent.mkdir(parents=True, exist_ok=True); source=sqlite3.connect('/app/data/portfolio.db'); backup=sqlite3.connect(target); source.backup(backup); result=backup.execute('PRAGMA integrity_check').fetchone()[0]; backup.close(); source.close(); print(f'{target} {result}')"
```

O resultado deve terminar em `ok`. Em seguida, copie o arquivo gerado para `/srv/pirata/cetruslabia/backups` e para um destino fora da maquina Pirata.

## Backup frio antes da primeira migracao

1. Confirme que nao ha jobs em execucao.
2. Pare somente o servico antigo que grava no banco.
3. Copie o diretorio de dados inteiro, incluindo `portfolio.db`, `portfolio.db-wal` e `portfolio.db-shm` quando existirem.
4. Preserve proprietario, permissoes e timestamps.
5. Valide uma copia do banco com `PRAGMA integrity_check`.
6. Registre o commit ou a imagem correspondente ao backup.

Nao copie apenas `portfolio.db` enquanto o processo estiver gravando.

## Restauracao

Restaurar um backup descarta dados gravados depois dele. Obtenha autorizacao explicita antes de prosseguir.

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
