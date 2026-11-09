# Guide: Model Comparison

Use this flow when the main doubt is not the prompt, but the target model. It responds: "Which model
delivers best result in this benchmark, considering cost and latency?"

## When to Use

- before running a long optimization;
- when you are choosing between SLM, small LLM and cloud model;
- when a cheap model looks good, but you need to measure regressions per case;
- when large input cost weighs on decision.

## Configure

State the candidates in `comparison_models`:

```yaml
comparison_models:
  - label: gemini-flash
    model:
      provider: google
      model_id: gemini-2.0-flash
      role: target
      params:
        temperature: 0.0
        max_tokens: 1024
      cost_per_million_input_tokens_usd: 0.10
      cost_per_million_output_tokens_usd: 0.40
  - label: gpt-mini
    model:
      provider: openai
      model_id: gpt-5-mini
      role: target
      api_mode: responses
      params:
        temperature: 0.0
        max_tokens: 1024
      cost_per_million_input_tokens_usd: 0.25
      cost_per_million_cached_input_tokens_usd: 0.025
      cost_per_million_output_tokens_usd: 2.00
```

In comparison mode, `target_model` and `reasoning_model` are not mandatory. Crucible uses each
`comparison_models` item as a temporary iteration target. They remain mandatory only when the same
file is also used for `validate`, `optimize` or `estimate-cost`.

## Run

```bash
uv run crucible compare-models \
  --prompt prompt.txt \
  --benchmark benchmark.yaml \
  --config config.yaml
```

It also works by the dashboard choosing `Compare` in `New run`, or by the API with `mode: compare`.

## What to Expect

The run generated has `run_mode: compare` and a iteration per model. The report shows:

- score and pass rate;
- total cost;
- p95 latency;
- cached tokens;
- best model per score;
- cheaper model;
- better value for money;
- winners per case.

The winner by value for money uses standard weights:

```yaml
comparison_value_quality_weight: 0.8
comparison_value_cost_weight: 0.2
comparison_value_latency_weight: 0.0
```

If the quality is non-negotiable, keep high weight in quality. If the goal is high-volume screening,
increase the cost weight.

## Next Step

After choosing the target, promote this model to `target_model` and run:

```bash
uv run crucible validate --config config.yaml
uv run crucible optimize --config config.yaml
```
