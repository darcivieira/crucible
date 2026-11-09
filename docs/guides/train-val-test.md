# Guide: Optimization With Train/Val/Test

Use split when you will repeatedly optimize and want to reduce overfitting to benchmark.

## Why Use

Without split, the prompt can improve in the set of cases used for refinement, but worsen in unseen
cases. This is especially common when the benchmark is large and the reasoning model receives
examples of flaws to rewrite the prompt.

With split:

- `train`: used to optimize.
- `val`: measures whether the best prompt found generalizes for cases that did not guide
  optimization.
- `test`: measures final result on a held-out set.

In practice, `optimize` stops using the entire benchmark to learn. It optimizes in `train`, chooses
the best prompt of this step and only then runs separate validations in `val` and `test`.

## Config

```yaml
use_benchmark_split: true
train_ratio: 0.7
val_ratio: 0.15
```

With 1000 cases and this configuration:

```text
train: 700 cases
val:   150 cases
test:  150 cases
```

The split is deterministic by `case.id`, so repeating the run keeps the split. This is good for
comparing executions, but requires caution: if the IDs are grouped by class, court, date or case
type, the split may get biased.

Bad example:

```text
notice-00001..00300 = Deadline
notice-00301..00600 = Hearing
notice-00601..01000 = None
```

In this case, `train` can see a different distribution from `val`/`test`. Before using split in
production, shuffle or intercalate the cases in benchmark, keeping IDs stable.

## Command

```bash
uv run crucible optimize --config examples/train-val-test/config.yaml
```

It is also possible to materialize split files:

```bash
uv run crucible split-benchmark \
  --benchmark benchmark.yaml \
  --output-dir ./splits \
  --train 0.7 \
  --val 0.15
```

This creates separate benchmarks for inspection, CI or manual execution. `optimize` with
`use_benchmark_split: true` does not need these files: it splits in memory.

## What to Expect

At the end, the run records:

- `validation_scores.train`
- `validation_scores.val`
- `validation_scores.test`
- `validation_scores.train_val_gap`

Interpretation:

- High `train` and low `val`: the prompt is probably overfitting the training examples.
- `train` low and `val` low: the prompt has not yet learned the expected behavior.
- `train`, `val` and `test` nearby: the prompt tends to generalize better.
- `test` should be looked at as final metric, not as a source of examples for new prompt.

## When Not To Use

Avoid split when the benchmark is too small. Crucible requires at least 3 cases, but this is only
the technical minimum. In practice, use split when each set still has enough diversity to represent
the problem.

For initial debugging of the provider, schema, and assertion, run `validate` or `optimize` without
splitting on a small subset. Then enable split to measure generalization.
