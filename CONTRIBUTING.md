# Contributing

Thank you for contributing to Crucible.

The project is local-first, Python 3.13, with CLI/SDK as main interfaces. Before opening PR, run
local checks.

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

Or run the main release checks:

```bash
bash scripts/release-check.sh
```

## How to Propose Changes

1. Open an issue if the change is large or changes public behavior.
2. Keep PRs focused.
3. Add or adjust tests for new behavior.
4. Update documentation and examples when UX changes.
5. Do not include `.crucible/`, local reports, credentials or outputs with sensitive data.

## Architecture Style

- Domain does not know CLI, FastAPI, SQLite or HTTP.
- Presentation stays thin: it parses input and calls application/adapters.
- Providers convert external payloads to `CompletionResult`.
- Assertions must be testable without external call whenever possible.

## Commits and Version

The project uses semantic versioning:

- patch: compatible bugfix;
- minor: new compatible feature;
- major: breaking API/contract change.

Public versions are published by GitHub Release/tag `vX.Y.Z`.

## Language

Use English for code identifiers, comments, docstrings, prompts, interface text,
examples, tests, and documentation. Keep documentation and examples consistent with
the public SDK, CLI, and API names.
