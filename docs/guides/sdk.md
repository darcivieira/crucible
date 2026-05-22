# Guia: Uso Via SDK

Use o SDK quando Crucible precisa entrar em outro produto, notebook, pipeline ou
teste automatizado.

## Fluxo Básico

```python
from crucible import Gabarito, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
gabarito = Gabarito.from_yaml("gabarito.yaml")

optimizer = Optimizer(config)
iteration = await optimizer.validate(prompt, gabarito)
run = await optimizer.optimize(prompt, gabarito)
```

## Quando Usar SDK Em Vez De CLI

- você quer injetar providers fake em testes;
- precisa usar store/cache customizados;
- quer montar gabaritos dinamicamente;
- está integrando Crucible em outro backend.

## Testes Sem Provider Real

```python
from crucible.modules.optimizer.adapters.providers.fake import FakeProvider

optimizer = Optimizer(
    config,
    target_provider=FakeProvider(lambda prompt: "ok"),
    reasoning_provider=FakeProvider(lambda prompt: "{}"),
)
```

## O Que Esperar

O SDK retorna objetos Pydantic completos: `Iteration`, `OptimizationRun`, `Verdict` e
`ScoreReport`. Eles podem ser serializados com `model_dump()` ou `model_dump_json()`.
