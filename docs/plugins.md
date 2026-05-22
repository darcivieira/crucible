# Plugins

Plugins estendem o Crucible sem alterar o pacote core.

Pontos de extensão atuais:

- assertions customizadas;
- importadores customizados.

Plugins são módulos Python carregados por `CRUCIBLE_PLUGIN_MODULES`.

```bash
CRUCIBLE_PLUGIN_MODULES=my_project.crucible_plugin uv run crucible validate ...
```

Múltiplos módulos:

```bash
CRUCIBLE_PLUGIN_MODULES=plugin_a,plugin_b uv run crucible optimize --config config.yaml
```

## Formato Do Plugin

Um módulo de plugin expõe:

```python
def register(registry):
    ...
```

## Assertion Customizada

Plugin:

```python
from crucible.modules.optimizer.domain.assertions import AssertionResult

def register(registry):
    async def min_length(expected, actual, config, context):
        minimum = int(config.get("minimum", 10))
        passed = len(actual) >= minimum
        return AssertionResult(
            score=1.0 if passed else 0.0,
            passed=passed,
            detail={"minimum": minimum, "actual_length": len(actual)},
        )

    registry.register_assertion("min_length", min_length)
```

Gabarito:

```yaml
assertion:
  type: plugin
  name: min_length
  config:
    minimum: 50
```

## Importador Customizado

Plugin:

```python
import json

from crucible import Contains, Gabarito, TestCase

def register(registry):
    def my_importer(text):
        payload = json.loads(text)
        return Gabarito(
            name="custom",
            version="imported",
            cases=[
                TestCase(
                    id=item["id"],
                    input=item["input"],
                    expected_output=item["expected"],
                    assertion=Contains(),
                )
                for item in payload["items"]
            ],
        )

    registry.register_importer("my_format", my_importer)
```

CLI:

```bash
CRUCIBLE_PLUGIN_MODULES=my_plugin \
  uv run crucible import-gabarito --source my_format --input data.json --output gabarito.yaml
```

## Tratamento De Erros

Erros de plugin sobem para o chamador. Em plugins usados em produção, envolva os
handlers com mensagens claras e testes de fixture.

## Testando Plugins

Use `FakeProvider` e gabaritos pequenos. Evite chamadas externas em testes de plugin.
