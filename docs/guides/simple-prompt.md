# Guide: Simple Prompt

Use this scenario when you already have a free text prompt and want to measure if it responds well
to known cases.

## When to Use

- You're creating a new prompt.
- The expected output is plain text.
- Validations can be deterministic, such as `contains`, `exact_match` or `regex`.
- You want to know if it's worth optimizing before you spend it on reasoning model.

## Files

`prompt.txt`:

```text
Classify the customer message and respond concisely.

Message:
{input}
```

`benchmark.yaml`:

```yaml
name: support-triage
version: v1
cases:
  - id: billing-001
    input: "I was charged twice this month."
    expected_output: "billing"
    assertion:
      type: contains
    tags: [billing]
```

## Flow

First, validate:

```bash
uv run crucible validate --prompt prompt.txt --benchmark benchmark.yaml --config config.yaml
```

`validate` responds if the current prompt already passes the benchmark. If it fails, look at the
cases, adjust assertions, or manually improve the prompt.

Then estimate cost:

```bash
uv run crucible estimate-cost --config config.yaml
```

Only then run:

```bash
uv run crucible optimize --config config.yaml
```

## What to Expect

- `v0` shows the performance of the original prompt.
- Subsequent versions show attempts to improve.
- The best prompt is preserved even if the last iteration gets worse.
- Reports show tags and cases that still fail.
