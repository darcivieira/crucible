# Referência CLI

Todos os comandos são executados com:

```bash
uv run crucible <comando>
```

## `init`

Cria um projeto inicial.

```bash
uv run crucible init ./my-project
```

Arquivos criados:

- `prompt.txt`
- `gabarito.yaml`
- `config.yaml`

## `validate`

Executa um prompt contra o gabarito sem refinamento.

```bash
uv run crucible validate \
  --prompt prompt.txt \
  --gabarito gabarito.yaml \
  --config config.yaml
```

Use antes de `optimize` para validar provider, prompt e gabarito.

## `optimize`

Executa o loop completo de otimização.

```bash
uv run crucible optimize --config config.yaml
```

Por padrão, `prompt.txt` e `gabarito.yaml` são carregados ao lado do `config.yaml`.

Com caminhos explícitos:

```bash
uv run crucible optimize \
  --config config.yaml \
  --prompt prompt_v0.txt \
  --gabarito regression.yaml
```

## `estimate-cost`

Estima custo antes da execução.

```bash
uv run crucible estimate-cost --config config.yaml
```

Com caminhos explícitos:

```bash
uv run crucible estimate-cost \
  --config config.yaml \
  --prompt prompt.txt \
  --gabarito gabarito.yaml
```

## `list-runs`

Lista runs recentes a partir do SQLite.

```bash
uv run crucible list-runs
uv run crucible list-runs --limit 50
```

## `show-run`

Mostra um resumo JSON da run.

```bash
uv run crucible show-run --run latest
uv run crucible show-run --run <run-id>
```

## `diff`

Mostra diff entre versões de prompt.

```bash
uv run crucible diff --run latest --from 0 --to best
uv run crucible diff --run <run-id> --from 1 --to 3
```

## `compare-runs`

Compara duas runs.

```bash
uv run crucible compare-runs <run-a> <run-b>
```

## `report`

Gera relatório.

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

Os arquivos são escritos em `.crucible/reports/`.

## `export`

Exporta artefatos da run.

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible export --run latest --format parquet --output ./verdicts.parquet
uv run crucible export --run latest --format pdf --output ./report.pdf
```

## `split-gabarito`

Cria arquivos determinísticos de train/val/test.

```bash
uv run crucible split-gabarito \
  --gabarito gabarito.yaml \
  --output-dir ./splits \
  --train 0.7 \
  --val 0.15
```

## `import-gabarito`

Converte formatos externos para o gabarito do Crucible.

```bash
uv run crucible import-gabarito --source jsonl --input cases.jsonl --output gabarito.yaml
uv run crucible import-gabarito --source promptfoo --input promptfoo.yaml --output gabarito.yaml
uv run crucible import-gabarito --source langsmith --input examples.json --output gabarito.yaml
uv run crucible import-gabarito --source dspy --input examples.json --output gabarito.yaml
```

## `serve`

Sobe o dashboard local.

```bash
uv run crucible serve
uv run crucible serve --host 0.0.0.0 --port 7777
```

URL padrão:

```text
http://127.0.0.1:7777
```

## `api`

Sobe a REST API local.

```bash
uv run crucible api --port 7788
```

O host padrão usa `CRUCIBLE_DASHBOARD_HOST` ou `127.0.0.1`.
