# Scoring

Crucible scoring combines response quality with operational metrics. Quality is calculated per test
case; cost, latency and tokens are added together with the score to leave explicit trade-offs.

## Basic Unit

Each `Verdict` contains:

- `score`: value between `0.0` and `1.0`.
- `passed`: Boolean defined by assertion.
- `test_case.weight`: Case weight in the global score.
- `execution`: latency, tokens, cost and output of the model.
- `assertion_detail`: specific assertion details.

The global iteration score is a weighted mean `0-100` scale.

```text
global_score = sum(score * weight) / sum(weight) * 100
```

There are two weight levels that should not be confused:

- `test_case.weight`: changes how much an entire case weighs on the global score.
- `field_by_field.weights`: changes how much each key weighs within the score of that case.

## Pass Rate Versus Score

`pass_rate` and `global_score` are not the same thing.

- `pass_rate`: percentage of cases with `passed=true`.
- `global_score`: weighted average scores, including partial scores.

This allows assertions like `field_by_field`, `embedding_similarity` and `llm_judge` to express
partial progress without turning everything into binary.

## Field Weights In JSON

When the answer is a JSON object, `field_by_field` can assign different weights for each key:

```yaml
expected_output: |
  {"classification": "Deadline", "text_validation": "Serve notice within 5 days."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

The score of the case is calculated by dividing the sum of the weights of correct fields by the
total weight:

```text
case_score = matched_field_weight / total_field_weight
```

In this example:

- correct `classification` and incorrect `text_validation`: `0.95` score;
- incorrect `classification` and correct `text_validation`: `0.05` score;
- both fields correct: `1.0` score;
- both fields incorrect: `0.0` score.

This is useful when one key is operationally more important than another. In a legal classification,
for example, `classification` can be worth 95% of the case and `text_validation` only 5%.

In practice:

- use `test_case.weight` when an entire case is more important than another;
- use `field_by_field.weights` when, within the same JSON, a key is more critical;
- Combine the two only when that intention is clear to who will review the report.

Current limitation: These weights affect the case score and therefore the `global_score`. Crucible
still does not expose a native global metric such as `classification_score` or a key-specific
threshold in `config.yaml`.

Today, the threshold set here:

```yaml
threshold: 95.0
```

continues to be applied to the run global score. To follow a specific key, use weights per field in
benchmark and export verdicts for external analysis, or model separate cases/tags for this
dimension.

There is also an important difference between partial score and case approval. The `field_by_field`
assertion marks `passed=true` only when all expected fields match. If `classification` is 95% and
`text_validation` is 5%, matching only `classification` produces `0.95` score, but the case still
appears
as partial failure. This is expected: `global_score` measures weighted progress; `pass_rate`
measures fully solved cases.

## Breakdown By Tag

Tags help answer where the prompt is failing.

```yaml
tags: [extraction, cnpj, formatted]
weight: 2.0
```

The report calculates score by tag using the cases that have that tag. If a case has multiple tags,
it contributes to all the corresponding groups.

Use tags for:

- type of task;
- domain entity;
- output format;
- difficulty level;
- origin of the case.

## Breakdown By Assertion Type

`by_assertion_type` shows aggregate score by type of validation:

- `exact_match`
- `contains`
- `regex`
- `numeric_match`
- `json_equal`
- `json_schema`
- `field_by_field`
- `pydantic_model`
- `embedding_similarity`
- `llm_judge`
- `llm_judge_with_rationale`
- `plugin`

This breakdown is useful to differentiate format failure, structural failure, and semantic failure.

## Output Format Versus Assertion

When the user configures `target_model.output_format`, the Crucible passes an output contract to the
provider. This can make the smaller model or SLM respond to JSON or adhere to a schema even before
the evaluation.

The assertion remains necessary. It is the empirical measurement of the contract:

- `output_format`: requests/enforces the format in the model call.
- `json_schema`: validates the structural contract; if `expected_output` is a payload and there is
  schema in
  `target_model.output_format`, validates expected/actual outputs against this schema and compares
  fields with
  uniform weight.
- `json_equal`: compares structures parsed by total equality.
- `field_by_field`: compares parsed object fields and allows partial score.

If you want priority by key, use `field_by_field.weights`. The `json_schema` path with expected
payload is a compatibility for automatically generated benchmarks and does not apply weights per
field.

`field_by_field`  also accepts `field_assertions` to choose the criterion by field. Without this
block, all fields use exact equality. With it, a closed field like `classification` can use `exact`,
while an open field as `text_validation` can use `contains`, `embedding_similarity`  or `llm_judge`.
The score of the case remains weighted by `weights`; the individual score of each field comes from
the set criterion.

This separation matters because not every provider guarantees schema with the same force, and some
models may partially ignore the contract.

In all structural cases, Crucible tries to parse common strings returned by LLMs: valid JSON, JSON
within Markdown blocks and simple literals with single quotes. Valid JSON with double quotes remains
the recommended format for versioned benchmarks.

## Worst Cases

`worst_case_ids` maintains up to 10 cases with lower score in iteration. These cases are useful for:

- prioritize human investigation;
- feeding diagnosis of the reasoning model;
- identify regressions;
- select new training or validation examples.

## Operational Metrics

Each `ScoreReport` also includes:

- `total_cost_usd`;
- `p50_latency_ms`;
- `p95_latency_ms`;
- `total_tokens`.

These metrics are calculated from case executions. They do not change the quality score today, but
appear in CLI, dashboard, reports and exports.

## Regressions

A verdict can be marked as `is_regression` when a passing case ceases to pass in a later iteration.
The run still returns the best seen prompt, but the regression marking helps to understand bad
changes caused by refinement.

## Repetition by Case

When `n_runs_per_case > 1`, the same case runs several times. Crucible uses majority vote to choose
representative output and records details in `assertion_detail["runs"]`, including:

- the amount of runs;
- distribution of outputs;
- winning output;
- latency deviation;
- flag `unstable`.

Use this when the provider is non-deterministic even with a low temperature.

## Recommended Interpretation

- High score at high cost may not be acceptable for production.
- High pass rate with low score indicates partial cases failing.
- A low score for a tag indicates a specific prompt gap.
- High P95 indicates operational risk even with good quality.
- Instability in repeated runs suggests reducing temperature, fixing seed or switching
  provider/configuration.

## Pareto Frontier

When `selection_strategy: multi_objective`, each iteration receives `objective_score`. The score
combines quality with cost and latency penalty:

```text
objective = quality * quality_weight - cost_norm * cost_weight - latency_norm * latency_weight
```

The run also records `pareto_frontier_versions`, containing versions not dominated by other
iteration in quality, cost and latency p95.
