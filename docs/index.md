# Crucible Documentation

Crucible is a local-first framework for empirically optimizing prompts against versioned benchmarks.

Use this index to find what you need.

## First Steps

- [User Guide](user-guide.md): Practical explanation for creating, validating, comparing, optimizing
  and inspecting prompts.
- [Quickstart](quickstart.md): Create a project, run an optimization and inspect the results.
- [End-to-end tutorial](tutorials/customer-support-end-to-end.md): Full flow of support triage,
  report and exports.
- [Concepts](concepts.md): understand prompt, benchmark, test case, assertion and run.
- [CLI Reference](cli.md): commands and flags available.
- [Configuration](configuration.md): full reference of `config.yaml`.

## Guides by Scenario

- [Simple prompt](guides/simple-prompt.md): free text evaluation and optimization.
- [Structured JSON output](guides/structured-json.md): `output_format` plus structural assertions.
- [LLM-as-Judge](guides/llm-as-judge.md): Subjective evaluation with a rubric.
- [Train/val/test](guides/train-val-test.md): reduce overfitting to benchmark.
- [Model comparison](guides/model-comparison.md): choose target by score, cost and value for money.
- [Provider Cache](guides/provider-cache.md): reduce cost with cached context.
- [Use in CI](guides/ci.md): pull requests regression validation.
- [Use via SDK](guides/sdk.md): Python programmatic integration.
- [Plugins](guides/plugins.md): assertions and domain importers.

## Authoring Evaluations

- [Benchmarks and Assertions](benchmarks-and-assertions.md): Write robust test cases.
- [Scoring](scoring.md): understand global score, weights, breakdowns and operational metrics.
- [Providers](providers.md): configure Ollama, OpenAI, Anthropic, Google, OpenRouter, vLLM and
  llama.cpp.
- [Importers and Exports](importers-and-exports.md): Move data in and out of the Crucible.

## Python, API, and Product

- [Python SDK](sdk.md): use Crucible programmatically.
- [REST API](api.md): create runs and see history via HTTP.
- [Dashboard](dashboard.md): inspect runs, verdicts, diffs and regressions.
- [Docker](docker.md): run the dashboard/API/CLI in a container and publish the image.
- [Operations](operations.md): local state, costs, secrets, CI, and cleanup.
- [Release](release.md): checks, smoke tests and artifacts for open source publication.
- [UX and Interfaces](interfaces.md): practical view of CLI, SDK, API, dashboard, reports and
  exports surfaces.

## Extensibility and Contribution

- [Plugins](plugins.md): assertions and custom importers.
- [Architecture and Implementation](architecture.md): code organization and flow.
- [Technical Decisions](technical-decisions.md): concurrency, cache, variance, budgets, persistence
  and current limits.
- [Development](development.md): tests, lint, typing and workflow.
- [Extension VSCode](../vscode-extension/): editor extension scaffold.

## Original Specification Mapping

- Item 2, Central Concepts: [Concepts](concepts.md).
- Item 4, Scoring System: [Scoring](scoring.md) and [Benchmarks and
  Assertions](benchmarks-and-assertions.md).
- Item 5, Architecture: [Architecture and Implementation](architecture.md).
- Item 8, Technical Decisions: [Technical Decisions](technical-decisions.md).
- Item 9, UX and Interfaces: [UX and Interfaces](interfaces.md).

## Examples

- [Local basic project](../examples/basic/)
- [Structured output with JSON Schema](../examples/structured-output/): contract, expected payload
  and field-by-field comparison.
- [Support Triage](../examples/customer-support-triage/)
- [LLM-as-judge for risk](../examples/llm-judge-risk/)
- [Train/val/test](../examples/train-val-test/)
- [Model comparison](../examples/model-comparison/)

## Community

- [Contributing](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Security](../SECURITY.md)
