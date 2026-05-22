# Contributing

Obrigado por contribuir com o Crucible.

O projeto é local-first, Python 3.13, com CLI/SDK como interfaces principais. Antes de
abrir PR, rode os checks locais.

## Setup

```bash
uv sync
npm --prefix vscode-extension install
```

## Checks

```bash
uv run ruff check .
uv run mypy src
uv run pytest
npm --prefix vscode-extension run compile
npm --prefix vscode-extension run package
```

Ou rode o pacote principal de release:

```bash
bash scripts/release-check.sh
```

## Como Propor Mudanças

1. Abra uma issue se a mudança for grande ou alterar comportamento público.
2. Mantenha PRs focados.
3. Adicione ou ajuste testes para comportamento novo.
4. Atualize documentação e exemplos quando a UX mudar.
5. Não inclua `.crucible/`, reports locais, credenciais ou outputs com dados sensíveis.

## Estilo De Arquitetura

- Domínio não conhece CLI, FastAPI, SQLite ou HTTP.
- Presentation é fina: parseia input e chama application/adapters.
- Providers convertem payloads externos para `CompletionResult`.
- Assertions devem ser testáveis sem chamada externa sempre que possível.

## Commits E Versão

O projeto usa versionamento semântico:

- patch: bugfix compatível;
- minor: nova feature compatível;
- major: quebra de API/contrato.

Versões públicas são publicadas por GitHub Release/tag `vX.Y.Z`.
