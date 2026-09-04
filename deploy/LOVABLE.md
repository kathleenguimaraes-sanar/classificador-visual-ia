# Publicacao no Lovable

## Destino

- workspace: `Piratas`;
- projeto: `CetrusLabIA`;
- URL pretendida: `https://cetruslabia.lovable.app`;
- repositorio: `kathleenguimaraes-sanar/CetrusLabIA`;
- branch de homologacao: `feat/lovable-backend-split`.

No levantamento de 2026-09-04, nao havia um projeto CetrusLabIA no workspace `Piratas`.

## Criacao e Git sync

1. Crie o projeto no workspace `Piratas` com o slug `cetruslabia`.
2. Em Project settings, conecte o GitHub ao repositorio existente.
3. Selecione `feat/lovable-backend-split` como branch ativa durante a homologacao.
4. Nao selecione `main` e nao solicite merge automatico.
5. Confirme que o Lovable reconheceu `package.json`, `vite.config.ts` e `src/` na raiz.
6. Confirme que alteracoes visuais ficam restritas ao frontend e nao removem `backend/`, `deploy/` ou `PLANO_IMPLANTACAO.md`.

O Lovable sincroniza uma branch ativa por vez. Antes de trocar a branch ativa, confirme que todas as alteracoes foram sincronizadas e revisadas no GitHub.

## Configuracao de producao

O repositorio contem `.env.production` com:

```text
VITE_API_BASE_URL=https://cetruslabia.tech-pirata.workers.dev
```

Essa URL e publica e nao e um segredo. Nao adicione chaves de IA, senha da aplicacao ou token do Cloudflare ao Lovable.

## Verificacao

1. Publique a branch de homologacao em `https://cetruslabia.lovable.app`.
2. Confirme que o login chama a API Workers.dev.
3. Confirme que o token fica apenas em memoria e que recarregar exige novo login.
4. Teste logout e expiracao da sessao.
5. Verifique desktop e mobile.
6. Confira no GitHub que o Lovable nao alterou a `main`.
