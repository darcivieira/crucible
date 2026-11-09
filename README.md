# Crucible

[![CI](https://github.com/darcijunior/crucible/actions/workflows/ci.yml/badge.svg)](https://github.com/darcijunior/crucible/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/crucible.svg)](https://pypi.org/project/crucible/)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Crucible is a pragmatic framework for empirical optimization of prompts. It executes a prompt
against a versioned benchmark, measures quality/cost/latency, uses a reasoning model to diagnose
failures, refines the prompt and maintains the best prompt found during the run.

The project is local-first: CLI and SDK are the main interfaces, SQLite saves the query history,
reports are static artifacts, and dashboard/API are optional local interfaces on the same data.

## What It Does

- Validates prompts against weighted test cases.
- Optimizes prompts using a `target_model` and a `reasoning_model`.
- Supports Ollama, OpenAI-compatible APIs, Anthropic, Google, OpenRouter, vLLM, llama.cpp and
  fake provider for testing.
- Persists runs in `.crucible/` for audit, comparison and reproducibility.
- Generates HTML, JSON and PDF reports.
- Exports verdicts in CSV/Parquet and the best prompt in text.
- Tracks the Pareto frontier for quality × cost × latency optimization.
- Suggests new benchmark cases from failures, regressions and instability.
- Offers CLI, Python SDK, local dashboard and REST API.
- Allows assertions and custom importers via plugins.
- Includes VSCode extension scaffold.

## Quickstart

The normal workflow starts with validation. First, check that the prompt, benchmark, and providers
work; then estimate the cost; finally, run optimization.

```bash
uv sync
uv run crucible init ./my-prompt
uv run crucible validate --prompt ./my-prompt/prompt.txt --benchmark ./my-prompt/benchmark.yaml --config ./my-prompt/config.yaml
uv run crucible estimate-cost --config ./my-prompt/config.yaml
uv run crucible optimize --config ./my-prompt/config.yaml
uv run crucible compare-models --config ./my-prompt/config.yaml
uv run crucible serve
```

Open `http://127.0.0.1:7777` to inspect the local history.

The template created by `init` uses Ollama as a target model and OpenAI as a reasoning model. Adjust
`config.yaml` before running if these providers are not available.

## Understanding the Workflow

`validate` answers: "Does the current prompt pass my benchmark?"

It executes the current prompt version, calculates its score, and checks the setup. Use it to debug
the benchmark, provider, assertion, and output format.

`optimize` answers: "Can Crucible improve this prompt?"

It executes the prompt, identifies failures, asks the `reasoning_model` for a diagnosis, generates a
new prompt version, and repeats until it reaches the threshold, budget, or another stopping
criterion. The run always preserves the best prompt found, which may differ from the latest version.

`compare-models` answers: "Which target offers the best quality, cost, and value on this benchmark?"
It uses `comparison_models` in `config.yaml` and runs one iteration per model without refinement.

## Minimal Use via SDK

```python
from crucible import Benchmark, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
benchmark = Benchmark.from_yaml("benchmark.yaml")

optimizer = Optimizer(config)
estimate = optimizer.estimate_cost(prompt, benchmark)
run = await optimizer.optimize(prompt, benchmark)
report_path = await optimizer.report(run.id, format="html")
```

## Local State

Crucible writes local state in `.crucible/`:

- `.crucible/crucible.sqlite`: searchable index of runs, iterations and verdicts.
- `.crucible/runs/`: full payloads, JSONL of iterations/verdicts and best prompt.
- `.crucible/reports/`: reports generated.
- `.crucible/cache/`: execution cache.

This is intentional. Run history is product data. Use `/tmp` only for disposable runs.

## Common Commands

```bash
uv run crucible estimate-cost --config ./my-prompt/config.yaml
uv run crucible validate --prompt prompt.txt --benchmark benchmark.yaml --config config.yaml
uv run crucible optimize --config config.yaml
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible report --run latest --format html
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible split-benchmark --benchmark benchmark.yaml --output-dir ./splits
uv run crucible serve
uv run crucible api --port 7788
```

## Documentation

Start here:

- [Documentation Index](docs/index.md)
- [Quickstart](docs/quickstart.md)
- [End-to-end tutorial](docs/tutorials/customer-support-end-to-end.md)
- [Concepts](docs/concepts.md)
- [CLI Reference](docs/cli.md)
- [Configuration](docs/configuration.md)
- [Benchmarks and Assertions](docs/benchmarks-and-assertions.md)
- [Scoring](docs/scoring.md)
- [Providers](docs/providers.md)
- [Python SDK](docs/sdk.md)
- [Dashboard](docs/dashboard.md)
- [REST API](docs/api.md)
- [Docker](docs/docker.md)
- [Plugins](docs/plugins.md)
- [Importers and Exports](docs/importers-and-exports.md)
- [Operations](docs/operations.md)
- [Release](docs/release.md)
- [Architecture and Implementation](docs/architecture.md)
- [Technical Decisions](docs/technical-decisions.md)
- [UX and Interfaces](docs/interfaces.md)
- [Development](docs/development.md)
- [Contribution](CONTRIBUTING.md)
- [Security](SECURITY.md)

Examples:

- [Basic project](examples/basic/)
- [Support Triage](examples/customer-support-triage/)
- [LLM-as-judge for risk](examples/llm-judge-risk/)
- [Train/val/test](examples/train-val-test/)
- [Structured output with JSON Schema](examples/structured-output/) with contract validation,
  expected payload and field-by-field comparison.

## License

Crucible is open source under MIT license.
