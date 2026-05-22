# Guia: Plugins

Use plugins quando você precisa validar ou importar algo específico do seu domínio
sem alterar o core do Crucible.

## Quando Usar

- uma assertion depende de uma regra interna;
- o gabarito vem de um formato proprietário;
- você quer experimentar comportamento sem manter um fork.

## Assertion Customizada

```python
from crucible.modules.optimizer.domain.assertions import AssertionResult

def register(registry):
    async def has_priority(expected, actual, config, context):
        priority = config.get("priority", "high")
        passed = priority in actual.lower()
        return AssertionResult(score=1.0 if passed else 0.0, passed=passed)

    registry.register_assertion("has_priority", has_priority)
```

Uso:

```yaml
assertion:
  type: plugin
  name: has_priority
  config:
    priority: high
```

## Carregar Plugin

```bash
CRUCIBLE_PLUGIN_MODULES=my_project.crucible_plugin \
  uv run crucible validate --prompt prompt.txt --gabarito gabarito.yaml --config config.yaml
```

## O Que Esperar

Erros do plugin sobem para o comando. Escreva testes com `FakeProvider` e fixtures
pequenas antes de usar em runs caras.
