# Quickstart

This guide takes you from an empty directory to an optimized and visible run on the local dashboard.

If you are new and want a more guided explanation, also read the [User Guide](user-guide.md).

## Prerequisites

- Python 3.13.
- `uv`.
- At least one provider for the target model.
- A reasoning provider for `optimize`; `validate` only needs the target.

For a first local execution with Ollama:

```bash
ollama pull gemma3:4b
```

For cloud models, export the corresponding key:

```bash
export CRUCIBLE_OPENAI_API_KEY=...
```

## Install Dependencies

At the root of the repository:

```bash
uv sync
```

## Create Project

```bash
uv run crucible init ./my-prompt
```

That creates:

```text
my-prompt/
  prompt.txt
  benchmark.yaml
  config.yaml
```

These three files are the core of the Crucible:

- `prompt.txt`: the prompt that will be evaluated and then optimized.
- `benchmark.yaml`: test cases that say what is a good answer.
- `config.yaml`: models, budget, parallelism and stopping criteria.

## Configure Models

Edit `./my-prompt/config.yaml`:

```yaml
target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target

reasoning_model:
  provider: openai
  model_id: gpt-5
  role: reasoning
```

If you still don't want to call a cloud reasoning model, start validating:

```bash
uv run crucible validate \
  --prompt ./my-prompt/prompt.txt \
  --benchmark ./my-prompt/benchmark.yaml \
  --config ./my-prompt/config.yaml
```

`validate` is the project's sanity check. It runs the current prompt against benchmark and shows
score, pass rate, cost and latency. If this command fails, correct provider, prompt, benchmark or
assertion before running `optimize`.

## Estimate Cost

```bash
uv run crucible estimate-cost --config ./my-prompt/config.yaml
```

The estimate is approximate. It uses a simple heuristic of tokens and the prices declared in each
`ModelSpec`.

## Compare Models

If you are still choosing the target model, configure `comparison_models` and run:

```bash
uv run crucible compare-models --config ./my-prompt/config.yaml
```

This command runs the same prompt against the same benchmark once per candidate model. It does not
optimize prompt. The goal is to decide the best target by score, cost and value for money before
starting a more expensive run of `optimize`.

## Optimize

```bash
uv run crucible optimize --config ./my-prompt/config.yaml
```

`optimize` is the step in which Crucible goes from evaluation to automatic improvement. It uses
`reasoning_model` to look at failed cases, identify error patterns, and propose a new version of the
prompt.

The Crucible will:

1. Run initial prompt.
2. Evaluate all benchmark cases.
3. Diagnose faults with the reasoning model.
4. Generate a refined prompt.
5. Repeat until you reach threshold, budget, time, plateau or maximum iterations.

The final result always points to the best prompt seen during the run.

This matters because a later iteration may get worse. History is saved, but the best prompt remains
the best version found.

## Inspect Results

```bash
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible report --run latest --format html
uv run crucible diff --run latest --from 0 --to best
```

Reports are written in `.crucible/reports/`.

Use `diff` to understand what has changed between the initial prompt and the best prompt. Use
`report` or the dashboard to see which cases have continued to fail and which have become
regression.

## Open Dashboard

```bash
uv run crucible serve
```

Open:

```text
http://127.0.0.1:7777
```

On the home screen you can open `New run` to run by the browser.

Use `Validate` when you want to quickly measure the current prompt. Use `Optimize` when you want
Crucible to propose better versions. Use `Compare` when you want to evaluate the `comparison_models`
models. The screen accepts local paths for `prompt.txt`, `benchmark.yaml` and `config.yaml`, or
content pasted in editors.

You can also choose host and port:

```bash
uv run crucible serve --host 0.0.0.0 --port 7777
```

Use `0.0.0.0` only on trusted network. Dashboard has no authentication.

## Use Local API

If you want to integrate Crucible with another system, start the API:

```bash
uv run crucible api --port 7788
```

Test with `curl`:

```bash
curl -s http://127.0.0.1:7788/runs
```

See full examples in [REST API](api.md).

## Export Artefacts

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible export --run latest --format parquet --output ./verdicts.parquet
uv run crucible report --run latest --format pdf
```

## Structured Output

When the model should respond in JSON following a schema, use the example in
`examples/structured-output/`. The default example covers the case where the benchmark brings the
expected payload in `expected_output`, while the schema stays in `config.yaml`.

OpenAI Responses API:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Ollama:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.yaml \
  --config ./examples/structured-output/config.ollama.yaml
```

This example uses three layers:

- `target_model.output_format`: requests JSON Schema from the provider.
- `expected_output`: saves the payload expected for that case.
- `assertion.type: json_schema`: validates expected/actual outputs against the configuration schema
  and compares parsed
  fields.

When you want to validate only the structural contract, without comparing expected values, use:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.schema.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

When you are writing the benchmark manually and want to leave explicit intent, use `field_by_field`:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.field-by-field.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## Recommended Workflow

1. Write or import a benchmark.
2. Run `validate` until setup, providers and assertions are correct.
3. Run `estimate-cost`.
4. If there is doubt about the target, run `compare-models`.
5. Run `optimize`.
6. Inspect failures and regressions on the dashboard.
7. Export the best prompt and verdicts.
8. Version the prompt/benchmark/config files, and keep `.crucible/` out of version control.
