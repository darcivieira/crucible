# Importers and Exports

## Importers

Importers convert external examples to `Benchmark`.

Command:

```bash
uv run crucible import-benchmark --source <source> --input <file> --output benchmark.yaml
```

Supported Sources:

- `jsonl`
- `promptfoo`
- `langsmith`
- `dspy`
- Sources registered by plugin

## JSONL

Input:

```jsonl
{"id":"case-001","input":"hello","expected_output":"world","tags":["smoke"]}
{"id":"case-002","question":"2+2","answer":"4"}
```

Command:

```bash
uv run crucible import-benchmark --source jsonl --input cases.jsonl --output benchmark.yaml
```

## Promptfoo

Minimal format supported:

```yaml
tests:
  - vars:
      input: hello
    assert:
      - type: contains
        value: world
```

Command:

```bash
uv run crucible import-benchmark --source promptfoo --input promptfoo.yaml --output benchmark.yaml
```

## LangSmith and DSPy

JSON format expected:

```json
{
  "examples": [
    {"id": "case-001", "inputs": {"input": "hello"}, "outputs": {"output": "world"}}
  ]
}
```

Lists are also accepted:

```json
[
  {"question": "2+2", "answer": "4"}
]
```

## Importer Limitations

Importers are pragmatic. They normalize common formats, but do not yet cover all variations of
Promptfoo, LangSmith or DSPy.

For strict migration, add tests with real fixtures of the source format.

Currently supported improvements:

- Promptfoo accepts `assert` or `assertions`, list or unique object.
- Promptfoo recognizes assertions `contains`, `equals`, `regex` and `json_schema`.
- Tags can be list, string or boolean map.
- LangSmith/DSPy accept `examples`, `data`, `rows`, `trainset`, `devset` and `demos`.
- Common inputs/outputs such as `input`, `question`, `query`, `inputs`, `outputs`, `answer`,
  `expected`, `label`, `x` and `y` are standardised.

## Exports

```bash
uv run crucible export --run latest --format csv --output verdicts.csv
uv run crucible export --run latest --format parquet --output verdicts.parquet
uv run crucible export --run latest --format prompt --output best_prompt.txt
uv run crucible export --run latest --format pdf --output report.pdf
```

## CSV and Parquet Columns

- `run_id`
- `iteration`
- `test_case_id`
- `score`
- `passed`
- `is_regression`
- `latency_ms`
- `tokens_in`
- `tokens_out`
- `cost_usd`
- `tags`
- `assertion_type`

## Reports

Reports are generated with:

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

The `report` command writes in `.crucible/reports/`.
