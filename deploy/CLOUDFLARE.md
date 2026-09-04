# Publicacao pelo Cloudflare

## Enderecos aprovados

- frontend: `https://cetruslabia.lovable.app`;
- API: `https://cetruslabia.tech-pirata.workers.dev`;
- destino local da API: `http://127.0.0.1:8106`.

Como Lovable e Workers.dev sao sites diferentes, a aplicacao usa token Bearer e nao depende de cookie cross-site.

## Arquitetura existente da Pirata

Os servicos publicados seguem este fluxo:

```text
<servico>.tech-pirata.workers.dev
  -> Worker Cloudflare exclusivo
  -> binding para VPC Service exclusivo
  -> named tunnel compartilhado piratas-fisica
  -> 127.0.0.1:<porta no no>
  -> servico local
```

Nao e necessario criar hostname publico no tunnel nem alterar seu token.

Nunca use quick tunnel (`cloudflared tunnel --url`): sua URL muda no restart. Tambem nao tente chamar `https://<uuid>.cfargotunnel.com` a partir do Worker, pois a Cloudflare bloqueia esse caminho. A integracao deve usar o binding de VPC Service.

## Estado desejado

No repositorio operacional `cluster-stacks`, acrescente `cetruslabia:8106` ao estado desejado de `tunnel/cloudflare/reconcile.sh` e ao loop de verificacao publica, seguindo o mesmo padrao dos servicos existentes.

Essa alteracao deve criar ou reconciliar:

- Worker `cetruslabia`;
- hostname `cetruslabia.tech-pirata.workers.dev`;
- VPC Service exclusivo para `127.0.0.1:8106`;
- binding do Worker para o VPC Service;
- uso do tunnel compartilhado `piratas-fisica`.

O MR da stack deve ser revisado pelo Pedro Mascarenhas antes da publicacao. Depois do merge aprovado, o CI do runner `pirata-fisica` faz o deploy e converge a configuracao Cloudflare. Nao execute a reconciliacao manualmente no host.

## Configuracao da aplicacao

O build do frontend usa:

```text
VITE_API_BASE_URL=https://cetruslabia.tech-pirata.workers.dev
```

O backend usa:

```text
CORS_ALLOWED_ORIGINS=https://cetruslabia.lovable.app
APP_AUTH_TRUST_PROXY_HEADERS=true
```

Mantenha `APP_AUTH_TRUST_PROXY_HEADERS=false` ate confirmar que a API local esta acessivel apenas pelo caminho esperado. Depois de habilitar o proxy confiavel, o rate limiting usa `CF-Connecting-IP`.

## Verificacao

```bash
curl --fail --show-error https://cetruslabia.tech-pirata.workers.dev/health
curl --output /dev/null --write-out '%{http_code}\n' https://cetruslabia.tech-pirata.workers.dev/api/status
```

Os resultados esperados sao HTTP 200 para `/health` e HTTP 401 para `/api/status` sem token.

Depois, abra `https://cetruslabia.lovable.app` e confirme login, preflight CORS, chamadas com `Authorization: Bearer` e logout. Outra origem nao deve receber autorizacao CORS.

Importacao e processamento de lotes devem continuar assincronos. Uma requisicao pelo edge Cloudflare nao pode ficar aberta aguardando trabalho longo por causa dos limites de timeout.
