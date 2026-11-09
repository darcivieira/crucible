# Guide: Use via SDK

Use SDK when Crucible needs to enter another product, notebook, pipeline or automated testing.

## Basic Flow

```python
from crucible import Benchmark, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
benchmark = Benchmark.from_yaml("benchmark.yaml")

optimizer = Optimizer(config)
iteration = await optimizer.validate(prompt, benchmark)
run = await optimizer.optimize(prompt, benchmark)
comparison = await optimizer.compare_models(prompt, benchmark)
```

## When to Use the SDK Instead of the CLI

- you want to inject fake providers into tests;
- need to use custom store/cache;
- you want to build benchmarks dynamically;
- you want to compare candidate models before choosing the target;
- you are integrating Crucible into another backend.

## Tests Without a Real Provider

```python
from crucible.modules.optimizer.adapters.providers.fake import FakeProvider

optimizer = Optimizer(
    config,
    target_provider=FakeProvider(lambda prompt: "ok"),
    reasoning_provider=FakeProvider(lambda prompt: "{}"),
)
```

## What to Expect

The SDK returns complete Pydantic objects: `Iteration`, `OptimizationRun`, `Verdict` and
`ScoreReport`. They can be serialized with `model_dump()` or `model_dump_json()`.

In comparison runs, `OptimizationRun.comparison_summary` brings the winners per score, cost and
value for money, in addition to the winners per case. For `compare_models`, `target_model` and
`reasoning_model` may be absent; for `validate` and `optimize`, both are required.
