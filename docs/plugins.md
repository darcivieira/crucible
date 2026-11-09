# Plugins

Plugins extend the Crucible without changing the core package.

Current extension points:

- custom assertions;
- custom importers.

Plugins are Python modules loaded by `CRUCIBLE_PLUGIN_MODULES`.

```bash
CRUCIBLE_PLUGIN_MODULES=my_project.crucible_plugin uv run crucible validate ...
```

Multiple modules:

```bash
CRUCIBLE_PLUGIN_MODULES=plugin_a,plugin_b uv run crucible optimize --config config.yaml
```

## Plugin Format

A plugin module exposes:

```python
def register(registry):
    ...
```

## Custom assertion

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

Benchmark:

```yaml
assertion:
  type: plugin
  name: min_length
  config:
    minimum: 50
```

## Custom Importer

Plugin:

```python
import json

from crucible import Contains, Benchmark, TestCase

def register(registry):
    def my_importer(text):
        payload = json.loads(text)
        return Benchmark(
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
  uv run crucible import-benchmark --source my_format --input data.json --output benchmark.yaml
```

## Error Handling

Plugin errors propagate to the caller. In plugins used in production, wrap the handlers with clear
messages and fixture tests.

## Testing Plugins

Use `FakeProvider` and small benchmarks. Avoid external calls in plugin tests.
