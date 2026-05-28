# SDK Python

O SDK é async-first.

## Otimização Básica

```python
from crucible import Gabarito, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
gabarito = Gabarito.from_yaml("gabarito.yaml")

optimizer = Optimizer(config)
run = await optimizer.optimize(prompt, gabarito)
```

## Validar Sem Refinamento

```python
iteration = await optimizer.validate(prompt, gabarito)
print(iteration.score)
```

## Comparar Modelos

```python
run = await optimizer.compare_models(prompt, gabarito)
print(run.comparison_summary.best_score.label)
print(run.comparison_summary.lowest_cost.label)
print(run.comparison_summary.best_value.label)
```

Use quando o `config.comparison_models` já contém os targets candidatos e você quer
uma avaliação única, sem refino, para decidir qual modelo vale promover.
Nesse fluxo, `target_model` e `reasoning_model` podem ficar ausentes do config.

## Estimar Custo

```python
estimate = optimizer.estimate_cost(prompt, gabarito)
print(estimate.estimated_total_cost_usd)
```

## Gerar Relatório

```python
path = await optimizer.report(run.id, format="html")
```

Formatos suportados:

- `html`
- `json`
- `pdf`

## Gabarito Programático

```python
from crucible import Contains, Gabarito, TestCase

gabarito = Gabarito(
    name="smoke",
    version="v1",
    cases=[
        TestCase(
            id="case-001",
            input="Diga apenas: ok",
            expected_output="ok",
            assertion=Contains(),
            tags=["smoke"],
        )
    ],
)
```

## Injetar Providers Em Testes

```python
from crucible.modules.optimizer.adapters.providers.fake import FakeProvider

optimizer = Optimizer(
    config,
    target_provider=FakeProvider(lambda prompt: "ok"),
    reasoning_provider=FakeProvider(lambda prompt: "{}"),
    judge_provider=FakeProvider(lambda prompt: '{"score": 1, "passed": true}'),
)
```

## Store Ou Cache Customizados

```python
from pathlib import Path

from crucible.modules.optimizer.adapters.cache import JsonlExecutionCache
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore

optimizer = Optimizer(
    config,
    store=SQLiteRunStore(Path(".crucible/custom.sqlite")),
    cache=JsonlExecutionCache(Path(".crucible/cache/executions.jsonl")),
)
```

## Exportar Dados

```python
from pathlib import Path

from crucible.modules.optimizer.application.exports import export_run

export_run(run, Path("verdicts.csv"), "csv")
export_run(run, Path("verdicts.parquet"), "parquet")
export_run(run, Path("best_prompt.txt"), "prompt")
```

## Carregar Runs

```python
run = await optimizer.load_run("latest")
run = await optimizer.load_run("<run-id>")
```

`latest` funciona quando o store suporta esse alias, como `SQLiteRunStore`.
