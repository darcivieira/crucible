# SDK Python

O SDK é async-first.

## Exemplo Completo

```python
import asyncio

from crucible import Gabarito, OptimizationConfig, Optimizer, Prompt


async def main():
    config = OptimizationConfig.model_validate({
        "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
        "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"},
    })
    prompt = Prompt(template="Responda apenas: {input}", variables=["input"])
    gabarito = Gabarito.model_validate({
        "name": "sample",
        "version": "v1",
        "cases": [
            {
                "id": "case-001",
                "input": "ok",
                "expected_output": "ok",
                "assertion": {"type": "contains"},
            }
        ],
    })

    optimizer = Optimizer(config)
    iteration = await optimizer.validate(prompt, gabarito)
    print(f"Score: {iteration.score:.2f}")


asyncio.run(main())
```

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
comparison_config = OptimizationConfig.model_validate({
    "comparison_models": [
        {
            "label": "fake-a",
            "model": {"provider": "fake", "model_id": "target-a", "role": "target"},
        },
        {
            "label": "fake-b",
            "model": {"provider": "fake", "model_id": "target-b", "role": "target"},
        },
    ]
})

run = await Optimizer(comparison_config).compare_models(prompt, gabarito)
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
