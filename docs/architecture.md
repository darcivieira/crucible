# Architecture

Crucible uses a pragmatic layered architecture, inspired by the `oneai` project.

```text
src/crucible/
  core/
  modules/
    optimizer/
      domain/
      application/
      adapters/
      presentation/
      plugins/
```

## Direction of Dependencies

```text
presentation -> application -> domain
adapters     -> domain
application  -> adapters only for default wiring
```

The domain does not know:

- HTTP;
- SQLite;
- CLI;
- FastAPI;
- filesystem.

## Domain

Files:

- `domain/models.py`
- `domain/assertions.py`
- `domain/scoring.py`
- `domain/protocols.py`

Responsibilities:


- Pydantic models;
- assertions;
- score aggregation;
- provider/cache/store protocols.

## Application

Files:

- `application/optimizer.py`
- `application/estimates.py`
- `application/reports.py`
- `application/exports.py`
- `application/execution_backends.py`

Responsibilities:


- optimization loop;
- internal diagnostic/refining prompts;
- cost estimate;
- generation of reports/exports;
- selection of execution backend.

## Adapters

Files:

- `adapters/providers/*`
- `adapters/storage.py`
- `adapters/cache.py`
- `adapters/importers.py`

Responsibilities:


- payloads and parsing of providers;
- rate limiting;
- SQLite and storage in files;
- cache;
- conversion of external formats.

## Presentation

Files:

- `presentation/cli/app.py`
- `presentation/web/app.py`
- `presentation/web/templates/*`
- `presentation/web/static/*`
- `presentation/api/app.py`

Responsibilities:


- parse user input;
- call application services;
- render terminal, HTML or JSON.

Optimization rule shouldn't live in that layer.

## Plugins

File:

- `plugins/registry.py`

Plugins register handlers in a local process registry.

## Optimization Flow

1. `Optimizer.optimize(prompt, benchmark)`.
2. Optionally divides benchmark into train/val/test.
3. Runs iteration `v0`.
4. Aggregates the score.
5. Stops on threshold, budget, time, plateau, or no failures.
6. Selects failures.
7. Diagnoses with the reasoning model.
8. Refines the prompt with the reasoning model.
9. Repeats.
10. Persists iterations and the final run.

## Storage Flow

Standard Store:

```python
CompositeRunStore(
    SQLiteRunStore(".crucible/crucible.sqlite"),
    FileRunStore(".crucible/runs"),
)
```

SQLite feeds CLI/API/dashboard queries. Files stay for human inspection and debugging.

## API Flow

`POST /runs`:

1. validates the request as Pydantic models;
2. creates `task_id`;
3. schedules `Optimizer.optimize(...)` as a FastAPI background task;
4. persists the run in SQLite.

Task state and completed run state are persisted in SQLite.
