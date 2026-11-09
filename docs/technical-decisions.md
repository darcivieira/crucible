# Technical Decisions

This document records Crucible’s main implementation decisions and their current status.

## Asyncio As a Base

The pipeline is async-first:

- providers expose asynchronous `complete(...)`;
- the optimizer executes cases in parallel;
- CLI calls the async flow with `asyncio.run`;
- API and dashboard run on FastAPI.

This keeps the core simple and works for both local and cloud providers.

## Rate Limit By Provider

Each `ModelSpec` declares limits:

```yaml
rate_limit:
  max_concurrent: 4
  requests_per_minute: 60
  retry_attempts: 2
  retry_backoff_seconds: 0.5
```

`RateLimitedProvider` enforces concurrency and requests per minute around the real provider. For
local GPU, use `max_concurrent: 1`; for cloud, increase according to the account limit.

## Retries for Transient Errors

HTTP providers retry transient responses:

- `429`
- `500`
- `502`
- `503`
- `504`

The backoff is exponential:

```text
retry_backoff_seconds * 2 ** attempt
```

Final errors are raised as `ProviderError`.

## Local Cache

The cache avoids paying again for identical executions. The key considers:

- prompt hash;
- case input;
- provider/model;
- hash of the model parameters.

The current adapter uses JSONL in `.crucible/cache/`, consistent with the local-first model.

## SQLite As a Persistent Index

SQLite is default because:

- does not require external service;
- works well with CLI and local SDK;
- feeds dashboard/API without parsing files;
- preserves history of runs for comparison.

Files in `.crucible/runs/` continue to exist for inspection and debugging. Postgres is a possible
evolution behind the same store contract.

## Static Reports

HTML, JSON, and PDF artifacts are generated from the persisted run. This allows:

- share result without starting the dashboard;
- attach reports to CI;
- archive decision snapshots.

Reports may contain sensitive data; treat it as a private artifact when the benchmark contains real
data.

## Variance and Determinism

Even with `temperature: 0.0`, quantized local models or remote providers may vary. Crucible offers:

- `seed` in `ModelParams` when the provider supports;
- `n_runs_per_case` for repetition;
- flag of instability in assertion details;
- train/val/test to reduce overfitting.

## Budget Enforcement

The optimizer stops for:

- `threshold_reached`;
- `max_iterations`;
- `budget_exhausted`;
- `time_exhausted`;
- `plateau`;
- `no_failures`.

`max_cost_usd`, `max_iterations` and `max_wallclock_seconds` must be configured for every real run.

## Run Backend

Backends available:

- `local`: `asyncio.gather` direct.
- `distributed`: local asynchronous pool limited by `distributed_workers`.
- `ray`: optional executor via Ray.
- `dask`: optional executor via Dask Distributed.

Ray/Dask run behind the same `ExecutionBackend` contract. As Python jobs need to be serializable for
these executors, workloads with customized providers should be tested before heavy use.

## Current Limits

- There is no formal SQLite schema migration.
- API has no authentication.
- Dashboard is simple server-side without SPA frontend.
- Structured observability exists through logs; OpenTelemetry has not yet been implemented.
