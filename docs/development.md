# Development

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

Optional smoke tests with real providers:

```bash
CRUCIBLE_RUN_PROVIDER_SMOKE=1 \
CRUCIBLE_SMOKE_PROVIDER=ollama \
CRUCIBLE_SMOKE_MODEL=gemma3:4b \
uv run pytest tests/test_provider_smoke.py
```

Expected baseline:

- tests pass;
- Ruff passes;
- mypy passes;
- Coverage remains sufficient to catch regressions.

## Test Strategy

Tests avoid real calls to providers.

Patterns used:

- `FakeProvider` for model calls;
- SQLite in temporary directories;
- CLI via `typer.testing.CliRunner`;
- API/dashboard via `fastapi.testclient.TestClient`.

## Add Features

Prefer this order:

1. model or domain protocol;
2. application behaviour;
3. adapter;
4. CLI/API/dashboard entry;
5. tests;
6. documentation.

## Add Provider

See [Providers](providers.md). Add tests to:

- payload format;
- response parsing;
- error treatment;
- registration at the factory.

## Add an Assertion

See [Benchmarks and Assertions](benchmarks-and-assertions.md). Add tests to:

- the case of success;
- the case of failure;
- invalid payload/details;
- YAML/Pydantic parsing of the discriminated union.

## Add CLI Command

Commands live in `presentation/cli/app.py`.

Keep commands thin:

- load files;
- validate arguments;
- call application/adapters;
- render output.

Don't put optimization logic into CLI.

## Add Page on Dashboard

Dashboard lives in `presentation/web/app.py`.

It should read from `SQLiteRunStore` or use application services. Avoid duplicating serialization
logic.

## Add Endpoint in API

API lives in `presentation/api/app.py`.

Maintain explicit request/response models. Durable state must pass through the stores.

## Known Technical Debt

- SQLite doesn't have a migration system yet.
- Contract tests from providers use mocks, not actual smoke tests.
- Importers cover common formats, not all upstream variations.
- Dashboard templates are embedded in Python for packaging simplicity.

## Release Checklist

Before posting a release:

1. Run all the checks.
2. Run the quickstart manually.
3. Generate an example HTML report.
4. Start the dashboard and API locally.
5. Update documentation.
6. Update changelog when it exists.
