# Benchmarks And Assertions

## Benchmark Format

```yaml
name: extraction-v1
version: "1.0"
description: Cases for extracting values from contracts.
cases:
  - id: case-001
    input: |
      Extract the CNPJ:
      ACME LTDA, CNPJ 12.345.678/0001-90.
    expected_output: "12.345.678/0001-90"
    assertion:
      type: exact_match
      normalize: true
    weight: 1.0
    tags: [extraction, cnpj]
    metadata:
      source: synthetic
```

## TestCase Fields

| Field | Mandatory | Meaning |
| --- | --- | --- |
| `id` | Yes | Stable identifier used in reports and regressions. |
| `input` | Yes | Input rendered in `{input}`. |
| `expected_output` | Yes | Expected response, schema or reference text. |
| `assertion` | Yes | Configuration of the evaluation rule. |
| `weight` | No | Case weight. Default: `1.0`. |
| `tags` | No | Groups for score breakdowns. |
| `metadata` | No | Free metadata. |

## How to Choose Assertion

Choose the cheapest option that captures the requirement:

1. deterministic;
2. structural;
3. semantics;
4. LLM-as-judge.

LLM-as-judge is useful, but costs more, is slower and needs calibration.

## Deterministic assertions

### `exact_match`

```yaml
assertion:
  type: exact_match
  normalize: true
  case_sensitive: true
```

Use for IDs, labels, strict values and standard strings.

### `contains`

```yaml
assertion:
  type: contains
  case_sensitive: false
```

Use `expected_output` as a substring.

### `regex`

```yaml
assertion:
  type: regex
  pattern: "\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}"
```

If `pattern` is omitted, `expected_output` is used as regex.

### `numeric_match`

```yaml
assertion:
  type: numeric_match
  tolerance: 0.01
```

Use for monetary values, counts and calculations.

### `json_equal`

```yaml
expected_output: '{"status":"ok"}'
assertion:
  type: json_equal
```

Compares parsed JSON structures.

Use when the entire value returned by the model needs to be equal to the expected JSON. Crucible
tries to parse valid JSON, JSON within Markdown blocks and simple literals with single quotes, but
valid JSON with double quotes remains the recommended format.

### `json_schema`

```yaml
expected_output: |
  {"type":"object","required":["status"]}
assertion:
  type: json_schema
```

It is also possible to declare schema inline:

```yaml
assertion:
  type: json_schema
  schema:
    type: object
    required: [status]
```

`json_schema` here is an assertion: it validates output after the model responds. To also ask the
provider to force structured output in the model call, use `target_model.output_format` in
`config.yaml`.

Do not use `json_schema` when `expected_output` is the expected payload:

```yaml
expected_output: '{"status":"ok","risk":"low"}'
assertion:
  type: field_by_field
```

In this case use `json_equal` for full equality or `field_by_field` to compare field by field with
partial score.

There is a pragmatic exception: when `target_model.output_format.type` is like `json_schema` in
`config.yaml`, but the generated benchmark came with `assertion.type: json_schema` and
`expected_output` contains the expected payload, Crucible uses the `config.yaml` schema to validate
both sides and compare parsed fields. This exists to support benchmarks coming from external
pipelines, but in manually written benchmarks prefer `field_by_field` or `json_equal`.

Typical example from generated YAML:

```yaml
expected_output: |
  {'classification': 'Deadline', 'text_validation': 'Serve notice within 5 days.'}
assertion:
  type: json_schema
```

With `target_model.output_format.type: json_schema`, this is not treated as inline schema. The value
is treated as expected payload, goes through parse along with the actual output and is compared
field by field.

When there are long texts, quotes or colons in the content, prefer YAML literal block with `|`
to avoid syntax error in the file:

```yaml
expected_output: |
  {'classification': 'Deadline', 'text_validation': 'Attach the document: updated proof.'}
```

## Structural assertions

### `field_by_field`

```yaml
expected_output: '{"status":"ok","risk":"low"}'
assertion:
  type: field_by_field
  weights:
    status: 2.0
    risk: 1.0
```

Compares JSON object fields and returns partial score. It is the most practical option when the
model returns a string containing JSON and the benchmark describes the expected fields such as
classification, status, risk or justification. Crucible parses both sides before comparing, so it
works even when the provider returns a string containing JSON instead of a materialized object.

#### Weights per Field

Use `weights` when not all keys are of the same importance. In structured extractions, class/label
is common to be more important than an auxiliary text:

```yaml
expected_output: |
  {"classification": "Deadline", "text_validation": "Serve notice within 5 days."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

The weights are proportional. The example above is equivalent to `0.95` and `0.05`. If the model
hits `classification` and misses `text_validation`, the case gets a `0.95` score. If you miss
`classification` and hit `text_validation`, you get `0.05`.

Fields not listed in `weights` receive weight `1.0`. Use positive weights and avoid ambiguous
settings like all fields with weight `0`. The field is only considered correct when the parsed
value is equal to the expected value; if the field is missing in the actual output, it counts as
error.

The `passed` of the case remains strict: in `field_by_field`, a partial response usually receives
partial score, but only passes when all expected fields hit. So it is possible to have
`global_score` rising while the `pass_rate` remains low.

#### Assertions By Field

By default, every field in `field_by_field` uses exact comparison. This preserves compatibility with
old benchmarks:

```yaml
assertion:
  type: field_by_field
```

equals:

```yaml
assertion:
  type: field_by_field
  field_assertions:
    classification:
      type: exact
    text_validation:
      type: exact
```

When a closed field should be evaluated quantitatively and another open field needs qualitative
evaluation, configure `field_assertions`:

```yaml
expected_output: |
  {"classification": "Deadline", "text_validation": "Serve notice within 5 days."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
  field_assertions:
    classification:
      type: exact
    text_validation:
      type: llm_judge
      threshold: 0.8
      rubric: >
        Check whether the extracted passage is present in the original input and is
        semantically equivalent to the expected value. Penalize inferences,
        invented paraphrases, or passages absent from the source text.
```

Types available by field:

- `exact`: exact equality of parsed value.
- `normalized_exact`: compares text by normalizing spaces; ignores case by default.
- `contains`: accepts when expected contains current or current contains expected.
- `embedding_similarity`: compares the field by similarity of embeddings.
- `llm_judge`: uses judge with field-specific rubric.

For `llm_judge`, Crucible sends to the judge the expected value, the extracted value and the
original input of the case. This allows us to evaluate whether a textual evidence actually came from
the source text, not only seems semantically plausible.

In `validate` and `optimize`, when `judge_models` is not informed, `reasoning_model` can serve as a
standard judge. In `compare`, `reasoning_model` is not required; therefore, if any
`field_assertions.*.type` is `llm_judge`, configure `judge_model` or `judge_models` explicitly.

This changes the case score, does not create a key-separated global metric. Today the global
`config.yaml` threshold continues to evaluate the aggregate run score. To highlight field
performance in reports, use complementary tags or export verdicts for external analysis.

If you need `classification` to represent 95% of the decision, prefer `field_by_field.weights`. The
pragmatic exception of `json_schema` with expected payload uses field-by-field comparison without
weights; it exists for automatically generated benchmarks, not to express key-to-key priority.

During `optimize`, these structured examples also help to assemble the task contract. If the
benchmark shows that `text_validation` must contain a literal snippet, the refiner cannot turn
this field into an inferred justification. If you try, the proposal is rejected and
`reasoning_model` receives the violations to generate another prompt, without new execution of the
target with the old prompt.

### `pydantic_model`

```yaml
assertion:
  type: pydantic_model
  schema:
    type: object
    required: [status]
```

Validates the schema first and then compares fields.

## Semantic Assertion

### `embedding_similarity`

```yaml
assertion:
  type: embedding_similarity
  threshold: 0.85
```

Requires an embedding provider in `AssertionContext`. The default CLI path does not set up embedding
provider automatically yet, so use via SDK or extend the Wiring of Providers.

## LLM-as-Judge

### `llm_judge`

```yaml
assertion:
  type: llm_judge
  rubric: >
    The response must correctly identify the risk and justify it based on the input.
  pass_threshold: 0.7
  position_swap: true
  calibration_examples:
    - expected: "high risk"
      actual: "high risk due to default"
      score: 0.9
```

By default, `position_swap` evaluates expected/actual in both orders to reduce position bias. If
`judge_models` has multiple models, the score is average and pass/fail uses simple consensus.

### `llm_judge_with_rationale`

Same behavior as `llm_judge`, with a focus on returning a detailed rationale.

## Assertion Via Plugin

```yaml
assertion:
  type: plugin
  name: my_assertion
  config:
    threshold: 3
```

See [Plugins](plugins.md).

## Tags & Weights

Use tags to make reports actionable:

```yaml
tags: [extraction, cnpj, formatted]
weight: 2.0
```

Good tags usually represent:

- family of the task;
- the concept of domain;
- difficulty;
- Output format.

## Benchmark as the Source of Truth in Optimize

During `optimize`, Crucible also uses the benchmark to build the task contract. This contract guides
`reasoning_model` and prevents the new prompt from degrading critical requirements.

Example: If `expected_output` shows that `text_validation` must contain the literal passage that led
to the classification, the refining should not turn this field into an inferred explanation. The
difference is:

- correct: `"text_validation": "Serve notice within 5 days."`
- Incorrect: `"text_validation": "The text contains a notice with a deadline."`

When the initial prompt does not explain this detail, the pattern observed in the benchmark is
treated as a source of truth for refining.

## Good Practice

- Keep `id` stable.
- Include simple cases, difficult cases and edge cases.
- Use deterministic assertions whenever possible.
- Enable train/val/test when repeatedly optimizing on the same benchmark.
- Do not leak examples of test set as few-shot on prompt.
- Keep expected outputs short and accurate, except in semantic assertions.
