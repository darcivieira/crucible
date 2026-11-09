# Concepts

## Prompt

Versioned template that will be rendered for each benchmark case.

```text
Respond concisely.

Input:
{input}
```

The most common placeholder is `{input}`. The content hash identifies versions in reports, cache,
and diffs.

## Benchmark

Versioned collection of test cases. It represents the empirical contract that the prompt needs to
comply with.

```yaml
name: sample
version: v1
cases:
  - id: case-001
    input: "Say only: ok"
    expected_output: "ok"
    assertion:
      type: contains
```

## TestCase

An individual case with:

- `id`: stable identifier.
- `input`: input rendered in the prompt.
- `expected_output`: expected response, schema or reference.
- `assertion`: evaluation rule.
- `weight`: weight on the global score.
- `tags`: groups for score breakdowns.

`weight` is the whole case weight. To weigh keys within a structured JSON, use `assertion.weights`
in `field_by_field`, not `weight`.

When the model output is structured, `expected_output` can be the expected payload:

```yaml
expected_output: |
  {'classification': 'Deadline', 'text_validation': 'Serve notice within 5 days.'}
assertion:
  type: json_schema
```

If `config.yaml` declares `target_model.output_format.type: json_schema`, Crucible uses the
configuration schema to validate expected/actual outputs and compare parsed fields. This allows you
to use automatically
generated benchmarks without rewriting each assertion.

When one key is more important than another, write the assertion explicitly:

```yaml
expected_output: |
  {"classification": "Deadline", "text_validation": "Serve notice within 5 days."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

## Assertion

Rule comparing `expected_output` to the actual output of the model. Assertions can be deterministic,
structural, semantic or LLM-as-judge-based.

Use the cheapest assertion that represents the requirement.

## TargetModel

Model whose behavior you want to improve with the prompt. It runs many times, so cost, latency, and
rate limits matter.

## ReasoningModel

Model used to diagnose failures and propose the next prompt. It runs fewer times, but is usually
more capable and more expensive.

## JudgeModel

Optional model used by assertions `llm_judge`. If unspecified, the default path uses the reasoning
model as the judge.

## OptimizationRun

Aggregate holding a complete execution:

- initial prompt;
- config;
- benchmark;
- iterations;
- best iteration;
- reason for stopping;
- validation scores when split is enabled.

When `use_benchmark_split` is enabled, the run optimizes using only the training split. After
selecting the best prompt, it validates that prompt on the `val` and `test` splits and records the
results in `validation_scores`.

## Iteration

One pass through the loop:

1. renders prompt;
2. executes cases;
3. evaluates assertions;
4. aggregates score;
5. optionally refines the prompt.

`v0` is the original prompt.

## Verdict

Result of a case in an iteration:

- score;
- pass/fail;
- model output;
- latency;
- tokens;
- cost;
- assertion detail;
- regression flag.

## Best-Ever

The run returns the best prompt ever seen, not necessarily the last generated prompt. This avoids
losing quality when a later iteration regresses.

## Local State

`.crucible/` is part of the product:

- SQLite for queries;
- files for human audit;
- reports for sharing;
- cache to avoid repeated calls.

Use `/tmp` only for disposable experiments.
