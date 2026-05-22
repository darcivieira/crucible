# Desenvolvimento

## Setup

```bash
uv sync
```

## Checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Smoke tests opcionais de providers reais:

```bash
CRUCIBLE_RUN_PROVIDER_SMOKE=1 \
CRUCIBLE_SMOKE_PROVIDER=ollama \
CRUCIBLE_SMOKE_MODEL=gemma3:4b \
uv run pytest tests/test_provider_smoke.py
```

Baseline esperado:

- testes passam;
- Ruff passa;
- mypy passa;
- cobertura continua suficiente para pegar regressões.

## Estratégia De Testes

Testes evitam chamadas reais a providers.

Padrões usados:

- `FakeProvider` para chamadas de modelo;
- SQLite em diretórios temporários;
- CLI via `typer.testing.CliRunner`;
- API/dashboard via `fastapi.testclient.TestClient`.

## Adicionar Features

Prefira esta ordem:

1. modelo ou protocolo de domínio;
2. comportamento de aplicação;
3. adapter;
4. entrada CLI/API/dashboard;
5. testes;
6. documentação.

## Adicionar Provider

Veja [Providers](providers.md). Adicione testes para:

- formato do payload;
- parsing de resposta;
- tratamento de erro;
- registro na factory.

## Adicionar Assertion

Veja [Gabaritos e Assertions](gabaritos-and-assertions.md). Adicione testes para:

- caso de sucesso;
- caso de falha;
- payload inválido/detalhes;
- parsing YAML/Pydantic do union discriminado.

## Adicionar Comando CLI

Comandos vivem em `presentation/cli/app.py`.

Mantenha comandos finos:

- carregar arquivos;
- validar argumentos;
- chamar application/adapters;
- renderizar output.

Não coloque lógica de otimização na CLI.

## Adicionar Página No Dashboard

Dashboard vive em `presentation/web/app.py`.

Ele deve ler de `SQLiteRunStore` ou usar serviços de application. Evite duplicar
lógica de serialização.

## Adicionar Endpoint Na API

API vive em `presentation/api/app.py`.

Mantenha modelos de request/response explícitos. Estado durável deve passar pelos
stores.

## Dívida Técnica Conhecida

- SQLite ainda não tem sistema de migração.
- Contract tests de providers usam mocks, não smoke tests reais.
- Importadores cobrem formatos comuns, não todas as variações upstream.
- Templates do dashboard estão embutidos em Python para simplicidade de empacotamento.

## Checklist De Release

Antes de taguear uma release:

1. Rode todos os checks.
2. Rode o quickstart manualmente.
3. Gere um relatório HTML de exemplo.
4. Suba dashboard e API localmente.
5. Atualize documentação.
6. Atualize changelog quando existir.
