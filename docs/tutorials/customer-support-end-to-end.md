# End-To-End Tutorial: Support Triage

This tutorial shows a complete flow: write prompt, create benchmark, validate, optimize, open report
and export the best prompt.

## Scenario

We want to classify support messages into operational categories:

- `billing`
- `technical`
- `account`
- `cancellation`
- `other`

## Files

Use the example:

```text
examples/customer-support-triage/
  prompt.txt
  benchmark.yaml
  config.yaml
```

## 1. Validate

```bash
uv run crucible validate \
  --prompt examples/customer-support-triage/prompt.txt \
  --benchmark examples/customer-support-triage/benchmark.yaml \
  --config examples/customer-support-triage/config.yaml
```

Expected result: a table with `v0` iteration, score, pass rate, cost and p95.

## 2. Estimate Cost

```bash
uv run crucible estimate-cost --config examples/customer-support-triage/config.yaml
```

Expected result: JSON with estimated tokens and approximate maximum cost.

## 3. Optimise

```bash
uv run crucible optimize --config examples/customer-support-triage/config.yaml
```

Expected result:

- history of iterations;
- run persisted in `.crucible/crucible.sqlite`;
- report HTML in `.crucible/reports/`;
- best preserved prompt.

## 4. Inspect

```bash
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible diff --run latest --from 0 --to best
uv run crucible report --run latest --format html
```

Open also:

```bash
uv run crucible serve
```

## 5. Export

```bash
uv run crucible export --run latest --format prompt --output best_prompt.txt
uv run crucible export --run latest --format csv --output verdicts.csv
```

## How to Read The Report

- Global score shows aggregate quality.
- Score by tag shows weak categories.
- Worst cases indicate where the prompt needs clearer examples or instruction.
- Regressions show cases that worsened after a change.

A good result is not only high score. Also check cost, latency p95 and if the final prompt remains
readable for maintenance.
