# UX And Interfaces

Crucible has four main surfaces: CLI, SDK, dashboard and REST API. All use the same domain models
and the same local persistence.

## CLI

CLI is the main interface for daily use.

Minimum flow:

```bash
uv run crucible init ./my-prompt
uv run crucible validate --prompt ./my-prompt/prompt.txt --benchmark ./my-prompt/benchmark.yaml --config ./my-prompt/config.yaml
uv run crucible estimate-cost --config ./my-prompt/config.yaml
uv run crucible optimize --config ./my-prompt/config.yaml
uv run crucible report --run latest --format html
```

Inspection commands:

```bash
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible diff --run latest --from 0 --to best
uv run crucible compare-runs <run-a> <run-b>
```

Data commands:

```bash
uv run crucible split-benchmark --benchmark benchmark.yaml --output-dir ./splits
uv run crucible import-benchmark --source jsonl --input cases.jsonl --output benchmark.yaml
uv run crucible export --run latest --format csv --output verdicts.csv
uv run crucible export --run latest --format prompt --output best_prompt.txt
```

## Python SDK

Use the SDK when integrating Crucible into another product, pipeline, or test.

```python
from crucible import Benchmark, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
benchmark = Benchmark.from_yaml("benchmark.yaml")

optimizer = Optimizer(config)
run = await optimizer.optimize(prompt, benchmark)
```

Use SDK for:

- inject fake providers in tests;
- control custom store/cache;
- build benchmarks programmatically;
- integrate with internal pipelines.

## Dashboard

The dashboard runs on SQLite and also starts local tasks.

```bash
uv run crucible serve
```

Use for:

- navigating runs;
- create runs `validate` and `optimize`;
- track tasks and cancellation;
- compare iterations;
- see best prompt;
- identify regressions;
- Inspect verdicts;
- filter history by status, target and score.

It should not be publicly exposed without external authentication.

## REST API

The API allows you to create runs and check history via HTTP.

```bash
uv run crucible api --port 7788
```

Main endpoints:

- `POST /runs`
- `GET /tasks/{task_id}`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/reports/{format}`

Today the API is suitable for local use or controlled internal integration. For multi-user
production, add authentication and user/workspace isolation policies.

## Reports

Reports are static artifacts:

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

Use HTML for human review, JSON for automation and PDF for shareable snapshot.

## Exports

Exports are focused on offline analysis or final prompt delivery:

```bash
uv run crucible export --run latest --format parquet --output verdicts.parquet
uv run crucible export --run latest --format csv --output verdicts.csv
uv run crucible export --run latest --format prompt --output best_prompt.txt
```

CSV/Parquet are useful for pandas, Polars, BI and regression audit.

## Interface Choice

| Need | Recommended interface |
| --- | --- |
| Run locally and iterate quickly | CLI |
| Integrate in Python or Tests | SDK |
| Visually inspect history | Dashboard |
| Integrate by HTTP | REST API |
| Share result | HTML/PDF Report |
| Analyze verdicts offline | CSV/Parquet |

## VSCode

The `vscode-extension/` directory contains the initial extension scaffold. It displays commands for
`validate`, `optimize` and `serve`, calling the CLI configured by `crucible.command`.
