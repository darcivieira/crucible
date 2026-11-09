# User Guide

This guide explains the Crucible from the point of view of those who want to improve or compare
prompts, without having to know the internal architecture of the project.

## What It Is For

Crucible helps you answer practical questions:

- Is my prompt delivering the expected response?
- Which model responds best to my case?
- Is it worth changing models for cost or quality?
- has the prompt improved from one version to another?
- What examples still fail?
- What was the best prompt found?

It does this by running a prompt against a set of expected examples, called `benchmark`.

## The Three Main Files

A Crucible project usually has:

```text
my-prompt/
  prompt.txt
  benchmark.yaml
  config.yaml
```

`prompt.txt` is the instruction sent to the model. Use `{input}` where the text of each case must
enter:

```text
Classify the text below.

Text:
{input}
```

`benchmark.yaml` contains test cases. Each case has an input, an expected response and a comparison
rule:

```yaml
name: example
version: v1
cases:
  - id: caso-001
    input: "Notify the party to respond within 5 days."
    expected_output: |
      {"classification": "Deadline", "text_validation": "within 5 days"}
    assertion:
      type: field_by_field
      weights:
        classification: 95
        text_validation: 5
      field_assertions:
        classification:
          type: exact
        text_validation:
          type: contains
```

`config.yaml` says which models will be used and what limits the execution must respect:

```yaml
threshold: 95.0
max_iterations: 3
max_cost_usd: 2.0

target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target

reasoning_model:
  provider: openai
  model_id: gpt-5
  role: reasoning
```

## Recommended Flow

1. Write a small benchmark with representative examples.
2. Run `validate` to see if the current prompt works.
3. If you are choosing model, run `compare-models`.
4. Run `optimize` to try to improve the prompt automatically.
5. Open the dashboard to understand failures, diffs, and the best prompt.
6. Export the best prompt and verdicts.

## Using CLI

Create a project:

```bash
uv run crucible init ./my-prompt
```

Validate the current prompt:

```bash
uv run crucible validate \
  --prompt ./my-prompt/prompt.txt \
  --benchmark ./my-prompt/benchmark.yaml \
  --config ./my-prompt/config.yaml
```

Compare candidate models:

```bash
uv run crucible compare-models \
  --prompt ./examples/model-comparison/prompt.txt \
  --benchmark ./examples/model-comparison/benchmark.yaml \
  --config ./examples/model-comparison/config.yaml
```

Optimize prompt:

```bash
uv run crucible optimize --config ./my-prompt/config.yaml
```

Generate a report:

```bash
uv run crucible report --run latest --format html
```

Export the best prompt:

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
```

## Using the Dashboard

Start the local server:

```bash
uv run crucible serve
```

Open in browser:

```text
http://127.0.0.1:7777
```

On the `New run` screen, choose:

- `Validate`: to measure the current prompt.
- `Optimize`: to ask Crucible to try to improve the prompt.
- `Compare`: to compare `comparison_models` models.

You can provide local paths to `prompt.txt`, `benchmark.yaml` and `config.yaml`, or paste the
content
directly into the screen editors.

## Using the API with Curl

Start the API:

```bash
uv run crucible api --port 7788
```

Create a validation run:

```bash
curl -s -X POST http://127.0.0.1:7788/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "validate",
    "prompt": {"template": "Respond with only: {input}", "variables": ["input"]},
    "benchmark": {
      "name": "smoke",
      "version": "v1",
      "cases": [
        {
          "id": "case-001",
          "input": "ok",
          "expected_output": "ok",
          "assertion": {"type": "contains"}
        }
      ]
    },
    "config": {
      "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
      "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"}
    }
  }'
```

The response includes a `task_id`. Check its status:

```bash
curl -s http://127.0.0.1:7788/tasks/<task-id>
```

When the task is finished, use the `run_id` returned to see the run:

```bash
curl -s http://127.0.0.1:7788/runs/<run-id>
```

## Using Python SDK

Create a `run_crucible.py` file:

```python
import asyncio

from crucible import Benchmark, OptimizationConfig, Optimizer, Prompt


async def main():
    config = OptimizationConfig.model_validate({
        "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
        "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"},
    })
    prompt = Prompt(template="Respond with only: {input}", variables=["input"])
    benchmark = Benchmark.model_validate({
        "name": "smoke",
        "version": "v1",
        "cases": [
            {
                "id": "case-001",
                "input": "ok",
                "expected_output": "ok",
                "assertion": {"type": "contains"},
            }
        ],
    })

    optimizer = Optimizer(config)
    iteration = await optimizer.validate(prompt, benchmark)
    print(iteration.score)


asyncio.run(main())
```

Run:

```bash
uv run python run_crucible.py
```

## Understanding the Score

The score goes from `0` to `100`.

In structured responses, use `field_by_field` to score field by field. Example:

```yaml
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
  field_assertions:
    classification:
      type: exact
    text_validation:
      type: contains
```

In this example, `classification` is worth 95% of the case and must match exactly. `text_validation`
is worth 5% and accepted when the expected snippet appears in the response or the response appears
in the expected snippet.

## Where the Results Are

Crucible records local state in `.crucible/`:

```text
.crucible/
  crucible.sqlite
  runs/
  reports/
  cache/
```

This allows you to open history, compare runs, generate reports, and recover the best prompt later.

## Next Steps

- To configure models: [Providers](providers.md).
- To write better benchmarks: [Benchmarks and Assertions](benchmarks-and-assertions.md).
- To compare models: [Model comparison](guides/model-comparison.md).
- To use API in integration: [REST API](api.md).
- To use in Python: [Python SDK](sdk.md).
