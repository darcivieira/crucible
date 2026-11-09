# Guide: Structured JSON Output

Use this scenario when the actual product contract requires JSON in a specific format.

## Central Idea

There are three different responsibilities:

- `output_format`: asks the provider to return JSON/schema.
- `json_schema` assertion: measures whether the output has actually fulfilled the contract.
- `json_equal` or `field_by_field`: measures whether the returned payload has the expected values.

Do not just trust the prompt to force JSON. When the provider supports structured output, state this
in `config.yaml`.

## Example

```yaml
target_model:
  provider: openai
  model_id: gpt-5-mini
  role: target
  api_mode: responses
  output_format:
    type: json_schema
    name: summary_output
    strict: true
    schema:
      type: object
      additionalProperties: false
      required: [summary, risk]
      properties:
        summary:
          type: string
        risk:
          type: string
          enum: [low, medium, high]
```

### Validate Contract Only

```yaml
assertion:
  type: json_schema
  schema:
    type: object
    required: [summary, risk]
```

This format validates whether the response has the expected shape, but does not compare specific
values.

### Compare the Expected Payload

```yaml
expected_output: '{"summary":"The customer promised to pay within 7 days.","risk":"low"}'
assertion:
  type: field_by_field
```

This format compares returned payload fields with expected fields.

When one key is more important than another, use weights:

```yaml
expected_output: |
  {"classification": "Deadline", "text_validation": "Serve notice within 5 days."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

Here, `classification` dominates the case score. This helps when the product needs to prioritize the
extracted class and treat auxiliary text as a secondary signal.

Threshold remains global:

```yaml
threshold: 95.0
```

This value does not mean "classification needs to beat 95%". It means "the run stops when the global
score reaches 95". The `classification: 95` weight makes this key represent 95% of the score of each
case
where it appears.

Example of reading:

- Correct `classification` and wrong `text_validation`: `0.95` case score;
- Wrong `classification` and correct `text_validation`: `0.05` Case Score;
- Both correct: `1.0` case score.

Even with a high partial score, the case only gets `passed=true` when all expected fields match. Use
`global_score` to see weighted progress and `pass_rate` to see how many cases have been fully
correct.

### Benchmark Generated With `json_schema`

When a benchmark is generated automatically and comes with `assertion.type: json_schema`, but
`expected_output` contains the expected payload, Crucible uses the schema declared in
`target_model.output_format` to validate expected/actual and compares parsed fields:

```yaml
expected_output: |
  {'summary': 'overdue payment with a promise to settle within 7 days', 'risk': 'medium'}
assertion:
  type: json_schema
```

Even if a smaller model returns a string with JSON inside, Crucible parses both sides before
comparing. Still, prefer to write the benchmark as valid JSON with double quotes.

This compatibility mode compares fields with uniform weight. If one key needs to be worth more than
another, switch the case assertion to `field_by_field` and declare `weights`.

## Command

Expected Payload using config schema:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Contract validation only:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.schema.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Explicit field by field comparison:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.field-by-field.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## What to Expect

- If the provider respects schema, the assertion must pass.
- If the provider generates invalid JSON, `json_schema` fails and the report shows the error.
- If the return has JSON parseable with values different from the benchmark, the contract passes,
  but the comparison of fields fails or receives partial score.
- If schema changes, the cache is invalidated automatically.
