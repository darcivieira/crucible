# Guide: Plugins

Use plugins when you need to validate or import something specific from your domain without changing
the Crucible core.

## When to Use

- an assertion depends on an internal rule;
- the benchmark comes from a proprietary format;
- You want to experiment with behavior without maintaining a fork.

## Custom assertion

```python
from crucible.modules.optimizer.domain.assertions import AssertionResult

def register(registry):
    async def has_priority(expected, actual, config, context):
        priority = config.get("priority", "high")
        passed = priority in actual.lower()
        return AssertionResult(score=1.0 if passed else 0.0, passed=passed)

    registry.register_assertion("has_priority", has_priority)
```

Usage:

```yaml
assertion:
  type: plugin
  name: has_priority
  config:
    priority: high
```

## Load Plugin

```bash
CRUCIBLE_PLUGIN_MODULES=my_project.crucible_plugin \
  uv run crucible validate --prompt prompt.txt --benchmark benchmark.yaml --config config.yaml
```

## What to Expect

Plugin errors propagate to the command. Write tests with `FakeProvider` and small fixtures before
using in
expensive runs.
