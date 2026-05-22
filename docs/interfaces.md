# UX E Interfaces

Crucible tem quatro superfícies principais: CLI, SDK, dashboard e REST API. Todas
usam os mesmos modelos de domínio e a mesma persistência local.

## CLI

A CLI é a interface principal para uso diário.

Fluxo mínimo:

```bash
uv run crucible init ./my-prompt
uv run crucible validate --prompt ./my-prompt/prompt.txt --gabarito ./my-prompt/gabarito.yaml --config ./my-prompt/config.yaml
uv run crucible estimate-cost --config ./my-prompt/config.yaml
uv run crucible optimize --config ./my-prompt/config.yaml
uv run crucible report --run latest --format html
```

Comandos de inspeção:

```bash
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible diff --run latest --from 0 --to best
uv run crucible compare-runs <run-a> <run-b>
```

Comandos de dados:

```bash
uv run crucible split-gabarito --gabarito gabarito.yaml --output-dir ./splits
uv run crucible import-gabarito --source jsonl --input cases.jsonl --output gabarito.yaml
uv run crucible export --run latest --format csv --output verdicts.csv
uv run crucible export --run latest --format prompt --output best_prompt.txt
```

## SDK Python

O SDK é indicado quando Crucible precisa entrar em outro produto, pipeline ou teste.

```python
from crucible import Gabarito, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
gabarito = Gabarito.from_yaml("gabarito.yaml")

optimizer = Optimizer(config)
run = await optimizer.optimize(prompt, gabarito)
```

Use o SDK para:

- injetar providers fake em testes;
- controlar store/cache customizados;
- construir gabaritos programaticamente;
- integrar com pipelines internos.

## Dashboard

O dashboard é read-only sobre SQLite.

```bash
uv run crucible serve
```

Use para:

- navegar runs;
- comparar iterações;
- ver best prompt;
- identificar regressões;
- inspecionar verdicts;
- filtrar histórico por status, target e score.

Ele não deve ser exposto publicamente sem autenticação externa.

## REST API

A API permite criar runs e consultar histórico via HTTP.

```bash
uv run crucible api --port 7788
```

Endpoints principais:

- `POST /runs`
- `GET /tasks/{task_id}`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/reports/{format}`

Hoje a API é adequada para uso local ou integração interna controlada. Para produção
multiusuário, adicione autenticação e políticas de isolamento por usuário/workspace.

## Reports

Reports são artefatos estáticos:

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

Use HTML para revisão humana, JSON para automação e PDF para snapshot compartilhável.

## Exports

Exports são voltados a análise offline ou entrega do prompt final:

```bash
uv run crucible export --run latest --format parquet --output verdicts.parquet
uv run crucible export --run latest --format csv --output verdicts.csv
uv run crucible export --run latest --format prompt --output best_prompt.txt
```

CSV/Parquet são úteis para pandas, Polars, BI e auditoria de regressões.

## Escolha Da Interface

| Necessidade | Interface recomendada |
| --- | --- |
| Rodar localmente e iterar rápido | CLI |
| Integrar em Python ou testes | SDK |
| Inspecionar histórico visualmente | Dashboard |
| Integrar por HTTP | REST API |
| Compartilhar resultado | Report HTML/PDF |
| Analisar verdicts offline | CSV/Parquet |

## VSCode

O diretório `vscode-extension/` contém o scaffold inicial da extensão. Ela expõe
comandos para `validate`, `optimize` e `serve`, chamando a CLI configurada por
`crucible.command`.
