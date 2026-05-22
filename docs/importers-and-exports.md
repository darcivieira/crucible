# Importadores E Exports

## Importadores

Importadores convertem exemplos externos para `Gabarito`.

Comando:

```bash
uv run crucible import-gabarito --source <source> --input <file> --output gabarito.yaml
```

Sources suportados:

- `jsonl`
- `promptfoo`
- `langsmith`
- `dspy`
- sources registrados por plugin

## JSONL

Input:

```jsonl
{"id":"case-001","input":"hello","expected_output":"world","tags":["smoke"]}
{"id":"case-002","question":"2+2","answer":"4"}
```

Comando:

```bash
uv run crucible import-gabarito --source jsonl --input cases.jsonl --output gabarito.yaml
```

## Promptfoo

Formato mínimo suportado:

```yaml
tests:
  - vars:
      input: hello
    assert:
      - type: contains
        value: world
```

Comando:

```bash
uv run crucible import-gabarito --source promptfoo --input promptfoo.yaml --output gabarito.yaml
```

## LangSmith E DSPy

Formato JSON esperado:

```json
{
  "examples": [
    {"id": "case-001", "inputs": {"input": "hello"}, "outputs": {"output": "world"}}
  ]
}
```

Listas também são aceitas:

```json
[
  {"question": "2+2", "answer": "4"}
]
```

## Limitações Dos Importadores

Os importadores são pragmáticos. Eles normalizam formatos comuns, mas ainda não
cobrem todas as variações de Promptfoo, LangSmith ou DSPy.

Para migração estrita, adicione testes com fixtures reais do formato de origem.

Melhorias suportadas atualmente:

- Promptfoo aceita `assert` ou `assertions`, lista ou objeto único.
- Promptfoo reconhece assertions `contains`, `equals`, `regex` e `json_schema`.
- Tags podem ser lista, string ou mapa booleano.
- LangSmith/DSPy aceitam `examples`, `data`, `rows`, `trainset`, `devset` e `demos`.
- Inputs/outputs comuns como `input`, `question`, `query`, `inputs`, `outputs`,
  `answer`, `expected`, `label`, `x` e `y` são normalizados.

## Exports

```bash
uv run crucible export --run latest --format csv --output verdicts.csv
uv run crucible export --run latest --format parquet --output verdicts.parquet
uv run crucible export --run latest --format prompt --output best_prompt.txt
uv run crucible export --run latest --format pdf --output report.pdf
```

## Colunas CSV E Parquet

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

Relatórios são gerados com:

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

O comando `report` escreve em `.crucible/reports/`.
