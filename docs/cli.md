# CLI Reference

All commands are executed with:

```bash
uv run crucible <comando>
```

## Common Workflows

Validate a prompt:

```bash
uv run crucible validate \
  --prompt prompt.txt \
  --benchmark benchmark.yaml \
  --config config.yaml
```

Compare models:

```bash
uv run crucible compare-models \
  --prompt prompt.txt \
  --benchmark benchmark.yaml \
  --config config.yaml
```

Optimize and open report:

```bash
uv run crucible optimize --config config.yaml
uv run crucible report --run latest --format html
```

Open dashboard:

```bash
uv run crucible serve
```

## `init`

Creates an initial project.

```bash
uv run crucible init ./my-project
```

Created files:

- `prompt.txt`
- `benchmark.yaml`
- `config.yaml`

## `validate`

Runs the current prompt against the benchmark without refinement.

Use `validate` when you want to answer:

- Does my `prompt.txt` render correctly?
- Is my `benchmark.yaml` well formed?
- Are the assertions evaluating what I expect?
- Is `target_model` accessible?
- What score does the current prompt achieve before optimization?

```bash
uv run crucible validate \
  --prompt prompt.txt \
  --benchmark benchmark.yaml \
  --config config.yaml
```

The command runs a single iteration, equivalent to the `v0` of an optimization. It:

1. renders the prompt for each case;
2. Calls `target_model`;
3. applies the assertion of the case;
4. calculates score, pass rate, cost, tokens and latency;
5. prints a table on the terminal.

It does not call `reasoning_model` to create a new prompt. This is why it is the right command to
debug setup before spending it on `optimize`.

## `optimize`

Run the complete optimization loop.

Use `optimize` when the setup has already been validated and you want Crucible to try to improve the
prompt automatically. Unlike `validate`, this command uses `reasoning_model` to diagnose failures
and propose new versions of the prompt.

```bash
uv run crucible optimize --config config.yaml
```

By default, `prompt.txt` and `benchmark.yaml` are loaded next to `config.yaml`.

With explicit paths:

```bash
uv run crucible optimize \
  --config config.yaml \
  --prompt prompt_v0.txt \
  --benchmark regression.yaml
```

The command:


1. executes the initial prompt;
2. calculates operational score and metrics;
3. builds a task contract from the initial prompt, config and benchmark;
4. selects relevant failures;
5. asks for a diagnosis from `reasoning_model`;
6. asks for a new prompt proposal;
7. validates the proposal against the contract of the task;
8. if the proposal violates the contract, ask the `reasoning_model` for repairs without running the
   target again;
9. executes the new version against benchmark only when refining is valid;
10. repeats until a stopping criterion is met.

The task contract protects requirements that should not change during optimization. Example: if the
prompt or benchmark indicates that a field should contain the literal snippet that justifies a
classification, the refining cannot exchange this for an inferred justification as "the text
contains term". In such cases, the benchmark is used as a source of truth when the initial prompt is
silent.

If `reasoning_model` generates an invalid prompt, Crucible does not create a new iteration with the
same prompt. It sends the violations back to the reasoning model and asks for a new proposal, up to
`max_refinement_repair_attempts`. If no attempt produces a valid prompt, the run closes with
`reasoning_failed_to_refine`.

During a run of `optimize`, Crucible maintains a local reasoning session. This session is by run,
not
global. It records diagnostics, proposals, raw response from the reasoning model, parse errors and
contract
violations. In the following calls, Crucible sends a summary of this history to `reasoning_model`,
so that it does not repeat rejected attempts and preserves previous decisions of the same execution.

Stopping criteria:

- `threshold_reached`: best score reached the threshold;
- `max_iterations`: iteration limit;
- `budget_exhausted`: maximum cost reached;
- `time_exhausted`: maximum time reached;
- `plateau`: score stopped improving;
- `no_failures`: there are no flaws to refine;
- `cancelled`: task cancelled by API;
- `reasoning_failed_to_refine`: the reasoning model failed to generate a prompt proposal that
  preserved the task contract.

At the end, the run is saved in `.crucible/` and the best prompt can be seen with `show-run`,
`report`, `diff`, `export` or the dashboard.

## `estimate-cost`

Estimates cost before execution.

```bash
uv run crucible estimate-cost --config config.yaml
```

With explicit paths:

```bash
uv run crucible estimate-cost \
  --config config.yaml \
  --prompt prompt.txt \
  --benchmark benchmark.yaml
```

## `list-runs`

List recent runs from SQLite.

```bash
uv run crucible list-runs
uv run crucible list-runs --limit 50
```

## `show-run`

Show a JSON run summary.

```bash
uv run crucible show-run --run latest
uv run crucible show-run --run <run-id>
```

## `diff`

Show diff between prompt versions.

```bash
uv run crucible diff --run latest --from 0 --to best
uv run crucible diff --run <run-id> --from 1 --to 3
```

## `compare-runs`

Compare two runs.

```bash
uv run crucible compare-runs <run-a> <run-b>
```

Use it when you already have two saved executions and want to compare the best score, amount of
iterations, total cost and stopping reason. It does not call any provider; it reads existing runs
in `.crucible/`.

## `compare-models`

Compares multiple target models using the same prompt and the same benchmark.

```bash
uv run crucible compare-models \
  --prompt prompt.txt \
  --benchmark benchmark.yaml \
  --config config.yaml
```

Use `compare-models` when you want to choose the best `target_model` before optimizing a prompt. The
command executes one iteration per entry in `comparison_models`, calculates score, pass rate, cost,
latency and cached tokens, and saves a run with `run_mode: compare`.

For this command, `target_model` and `reasoning_model` may be missing from `config.yaml`. Crucible
uses each item of `comparison_models` as a temporary target. When promoting the winner to `validate`
or `optimize`, configure `target_model` and `reasoning_model`.

The result shows three winners:

- Best score: prioritizes quality;
- lower cost: prioritizes total cost;
- Best value for money: uses the `comparison_value_*` weights of config.

It does not ask the `reasoning_model` for refinement. The comparison is a controlled snapshot: same
prompt, same cases, one target at a time. After choosing the winning model, run `validate` or
`optimize` with this model as `target_model`.

## `report`

Generates report.

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

The files are written in `.crucible/reports/`.

## `export`

Exports run artifacts.

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible export --run latest --format parquet --output ./verdicts.parquet
uv run crucible export --run latest --format pdf --output ./report.pdf
```

## `split-benchmark`

Create train/val/test deterministic files for manual inspection or execution.

```bash
uv run crucible split-benchmark \
  --benchmark benchmark.yaml \
  --output-dir ./splits \
  --train 0.7 \
  --val 0.15
```

This command materializes the same rule used by `use_benchmark_split: true`: the cases are ordered
by `case.id`, then cut into train, val and test. With 1000 cases, `--train 0.7 --val 0.15` generates
700/150/150.

Use the command when you want to review the split, edit explicit splits or run separate validations
in CI. For normal flow of `optimize`, just enable `use_benchmark_split` in config.

## `import-benchmark`

Convert external formats to the Crucible benchmark.

```bash
uv run crucible import-benchmark --source jsonl --input cases.jsonl --output benchmark.yaml
uv run crucible import-benchmark --source promptfoo --input promptfoo.yaml --output benchmark.yaml
uv run crucible import-benchmark --source langsmith --input examples.json --output benchmark.yaml
uv run crucible import-benchmark --source dspy --input examples.json --output benchmark.yaml
```

## `serve`

Starts the local dashboard.

```bash
uv run crucible serve
uv run crucible serve --host 0.0.0.0 --port 7777
```

Default URL:

```text
http://127.0.0.1:7777
```

## `api`

Starts the local REST API.

```bash
uv run crucible api --port 7788
```

The default host uses `CRUCIBLE_DASHBOARD_HOST` or `127.0.0.1`.
