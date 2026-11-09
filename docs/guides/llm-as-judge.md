# Guide: LLM-as-Judge

Use LLM-as-judge when the correct answer is too subjective for `contains`, `regex` or JSON
comparison.

## When to Use

- Summaries.
- Risk analysis.
- Answers with justification.
- Tasks where there are multiple acceptable answers.

Avoid LLM-as-judge when a deterministic assertion meets the requirement. It is slower, more
expensive and needs a clear rubric.

## Benchmark

```yaml
assertion:
  type: llm_judge
  rubric: >
    The response must correctly identify the risk, justify it with evidence from
    the input, and avoid inventing facts.
  pass_threshold: 0.75
  position_swap: true
```

`position_swap` evaluates expected/actual in two orders to reduce position bias.

## Config

```yaml
judge_models:
  - provider: openai
    model_id: gpt-5
    role: judge
```

If `judge_models` is not configured, Crucible uses `reasoning_model`.

## What to Expect

- The score becomes partial, from `0.0` to `1.0`.
- The report includes judge payloads.
- Cost goes up, because each evaluation calls for a judge model.
- Use few cases first and increase when the rubric is stable.
