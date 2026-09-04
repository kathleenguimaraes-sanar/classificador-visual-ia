# Implantacao na maquina Pirata

O repositorio GitLab `sanardigital/pirata/infra-pirata/cluster-stacks` e a unica fonte de verdade da implantacao. Este repositorio descreve apenas o contrato da aplicacao; nao contem manifest de producao nem arquivo com segredos.

Antes de qualquer operacao na maquina Pirata, carregue a skill `maquina-pirata`. Nao instale, configure, suba containers ou altere o host manualmente.

## Fluxo

1. Finalize e homologue o commit da aplicacao.
2. Crie ou ajuste a stack `cetruslabia` no `cluster-stacks`.
3. Versione `stack.yml`, `secrets.map`, persistencia e healthcheck, sem expor o servico ainda.
4. Abra MR e aguarde o CI ficar verde.
5. Envie o MR e o nome da stack ao Pedro Mascarenhas para revisao.
6. Somente depois da aprovacao e do merge, deixe o runner `pirata-fisica` fazer o deploy e as verificacoes.
7. Depois de o servico estar saudavel, abra uma alteracao separada para Worker/VPC Service e publique o frontend Lovable.

Hermes nao participa deste servico, pois ele nao e um servico de agente.

## Contrato da stack

- imagem imutavel identificada pelo commit homologado;
- API publicada na porta de host reservada pelo `cluster-stacks`;
- `CETRUS_DATA_DIR=/app/data` em armazenamento persistente;
- diretorio persistente contendo `portfolio.db` e seus arquivos WAL/SHM;
- restart policy e healthcheck em `/health`;
- parada graciosa suficiente para encerrar o processamento atual;
- nenhuma dependencia de GPU ou Ollama em producao;
- nenhuma credencial em variavel versionada ou arquivo `.env`.

## Configuracao e secrets

Configuracoes nao secretas ficam no `stack.yml`. Credenciais ficam no 1Password e sao entregues como Docker Secrets por `secrets.map`; os valores nao podem tocar Git, Slack, CI ou arquivos locais.

Secrets esperados:

- senha da aplicacao;
- segredo de assinatura das sessoes;
- chaves dos provedores de IA habilitados;
- token de delivery do JW Player, se necessario.

## Exposicao externa

Use o named tunnel `piratas-fisica`, Worker e binding de VPC Service. Nunca use quick tunnel nem acesse um hostname `<uuid>.cfargotunnel.com` a partir do Worker. O procedimento esta em `deploy/CLOUDFLARE.md`.

Processamentos longos continuam no backend como jobs assincronos; nenhuma requisicao sincronica pelo edge deve aguardar o lote completo.

## Criterios antes de publicar

- stack e configuracao versionadas no `cluster-stacks`;
- MR revisado e CI verde;
- deploy executado pelo runner `pirata-fisica`;
- secrets entregues por 1Password e Docker Secrets;
- dados persistentes, backup e restart validados;
- `/health` retorna HTTP 200 e `/api/status` sem token retorna HTTP 401;
- hostname estavel validado pelo Worker/VPC Service;
- logs e smoke test de producao verificados.

Nao ha garantia de zero downtime: fila, sessoes da aplicacao e login do JW Player ficam em memoria. Atualizacoes exigem uma parada curta e novo login.
