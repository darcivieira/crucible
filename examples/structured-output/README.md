# Structured Output

This example shows three ways to test a structured response.

## 1. Expected Payload with `json_schema`

Use `benchmark.yaml` when the benchmark comes from a pipeline that already fills the
`expected_output` with the expected response:

```yaml
expected_output: |
  {'summary': 'overdue payment with a promise to settle within 7 days', 'risk': 'medium'}
assertion:
  type: json_schema
```

As `config.*.yaml` declares `target_model.output_format.type: json_schema`, Crucible uses the config
schema to validate expected/actual and compares parsed fields. This covers responses received as a
string containing JSON or literal similar to Python.

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## 2. Schema As Benchmark

Use `benchmark.schema.yaml` when you want to validate only if the output respects the structural
contract:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.schema.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## 3. Explicit Field-by-Field Comparison

Use `benchmark.field-by-field.yaml` when you control the benchmark manually and want to make it
clear:

```yaml
assertion:
  type: field_by_field
  weights:
    risk: 95
    summary: 5
```

In this example, `risk` dominates the case score. In a classifier, the same pattern could be
`classification: 95` and `text_validation: 5`.

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.field-by-field.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## Ollama

Switch the configuration to `config.ollama.yaml` to run the same flow with Ollama:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --benchmark ./examples/structured-output/benchmark.yaml \
  --config ./examples/structured-output/config.ollama.yaml
```
