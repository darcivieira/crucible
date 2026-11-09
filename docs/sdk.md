# Python SDK

The SDK is async-first.

## Complete Example

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
        "name": "sample",
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
    print(f"Score: {iteration.score:.2f}")


asyncio.run(main())
```

## Basic Optimization

```python
from crucible import Benchmark, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
benchmark = Benchmark.from_yaml("benchmark.yaml")

optimizer = Optimizer(config)
run = await optimizer.optimize(prompt, benchmark)
```

## Validate Without Refining

```python
iteration = await optimizer.validate(prompt, benchmark)
print(iteration.score)
```

## Compare Models

```python
comparison_config = OptimizationConfig.model_validate({
    "comparison_models": [
        {
            "label": "fake-a",
            "model": {"provider": "fake", "model_id": "target-a", "role": "target"},
        },
        {
            "label": "fake-b",
            "model": {"provider": "fake", "model_id": "target-b", "role": "target"},
        },
    ]
})

run = await Optimizer(comparison_config).compare_models(prompt, benchmark)
print(run.comparison_summary.best_score.label)
print(run.comparison_summary.lowest_cost.label)
print(run.comparison_summary.best_value.label)
```

Use it when `config.comparison_models` already contains the candidate targets and you want a single
evaluation without refinement to decide which model is worth promoting. In this stream,
`target_model` and
`reasoning_model` may be absent from config.

## Estimate Cost

```python
estimate = optimizer.estimate_cost(prompt, benchmark)
print(estimate.estimated_total_cost_usd)
```

## Generate Report

```python
path = await optimizer.report(run.id, format="html")
```

Supported formats:

- `html`
- `json`
- `pdf`

## Create a Benchmark Programmatically

```python
from crucible import Contains, Benchmark, TestCase

benchmark = Benchmark(
    name="smoke",
    version="v1",
    cases=[
        TestCase(
            id="case-001",
            input="Say only: ok",
            expected_output="ok",
            assertion=Contains(),
            tags=["smoke"],
        )
    ],
)
```

## Inject Providers In Tests

```python
from crucible.modules.optimizer.adapters.providers.fake import FakeProvider

optimizer = Optimizer(
    config,
    target_provider=FakeProvider(lambda prompt: "ok"),
    reasoning_provider=FakeProvider(lambda prompt: "{}"),
    judge_provider=FakeProvider(lambda prompt: '{"score": 1, "passed": true}'),
)
```

## Custom Store or Cache

```python
from pathlib import Path

from crucible.modules.optimizer.adapters.cache import JsonlExecutionCache
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore

optimizer = Optimizer(
    config,
    store=SQLiteRunStore(Path(".crucible/custom.sqlite")),
    cache=JsonlExecutionCache(Path(".crucible/cache/executions.jsonl")),
)
```

## Export Data

```python
from pathlib import Path

from crucible.modules.optimizer.application.exports import export_run

export_run(run, Path("verdicts.csv"), "csv")
export_run(run, Path("verdicts.parquet"), "parquet")
export_run(run, Path("best_prompt.txt"), "prompt")
```

## Load Runs

```python
run = await optimizer.load_run("latest")
run = await optimizer.load_run("<run-id>")
```

`latest` works when the store supports this alias, such as `SQLiteRunStore`.
