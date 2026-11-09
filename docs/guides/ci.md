# Guide: Use in CI

Use Crucible in CI to prevent prompt regressions before publishing changes.

## Recommended Strategy

In CI, prefer `validate`, not `optimize`.

`validate` is predictable: it measures the current prompt and fails quickly if the
provider/benchmark breaks.
`optimize` can consume more time and cost.

## Example GitHub Actions

```yaml
name: Prompt Regression

on:
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: |
          uv run crucible validate \
            --prompt prompt.txt \
            --benchmark benchmark.yaml \
            --config config.yaml
      - run: uv run crucible report --run latest --format html
```

## What to Save as Artifact

- `.crucible/reports/*.html`
- CSV/Parquet exports if there is further analysis

Do not publish reports if the benchmark has sensitive data.
