# Dashboard

The dashboard is a local FastAPI application on `.crucible/crucible.sqlite`.

Start it with:

```bash
uv run crucible serve
```

Default URL:

```text
http://127.0.0.1:7777
```

To choose host and port:

```bash
uv run crucible serve --host 0.0.0.0 --port 7777
```

Step by step:

1. Run `uv run crucible serve`.
2. Open `http://127.0.0.1:7777`.
3. Click `New run`.
4. Choose `Validate`, `Optimize` or `Compare`.
5. Provide local paths or paste the contents of `prompt`, `benchmark` and `config`.
6. Monitor the task until it completes.
7. Open the run to see score, verdicts, diffs, prompts and reports.

Dashboard is local and has no authentication. Use on a trusted network.

## What Changed

The dashboard is no longer just a read-only listing. It now also helps create local executions,
track tasks, interpret results and decide where to look first.

Use the UI when you want:

- run `validate` without leaving the browser;
- start `optimize` with local files or pasted content;
- compare target models with the same prompt and benchmark;
- monitor status/cancellation of tasks;
- understand why a run stopped;
- filter verdicts by failure, regression, tag, assertion and score;
- generate HTML/JSON/PDF report from run screen.

## Main Pages

### `/`

List of runs with summary cards:

- total runs;
- runs in progress;
- Runs completed;
- best recent score;
- total cost of the listed runs.

Filters by query string:

- `status`
- `target`
- `min_score`

Example:

```text
http://127.0.0.1:7777/?status=completed&target=ollama&min_score=80
```

### `/runs/{run_id}`

Show:

- Run mode (`Validate`, `Optimize` or `Compare`);
- status;
- stop reason with more legible description;
- best score;
- pass rate;
- threshold;
- total cost;
- P95 latency;
- target/reasoning model;
- next step suggestion;
- contract of the task and preserved invariants;
- progress by iteration;
- Worst cases and weaker tags;
- Iteration table;
- Best prompt.

In comparison runs, the screen also shows a `Model comparison` block with:

- winner by best score;
- winner at lower cost;
- winner for best value for money;
- score, pass rate, cost, p95 and tokens cached by model;
- winner per case.

Use this screen to respond quickly:

- Has the run reached its goal?
- Did it stop because of a plateau, the budget, or the iteration limit?
- Is the score high while the pass rate is still low?
- Which cases should be investigated first?

When a refining proposal is rejected for violating the task contract, the iterations table shows the
reason. This usually indicates semantic drift, such as replacing literal extraction for explanation
or
remove a rule from "do not invent".

If there are attempts to repair, the same table shows a badge with the number of repairs and an
expandable block with the violations returned to `reasoning_model`. Use this to understand whether
the model corrected the prompt after feedback or whether the run stopped with
`reasoning_failed_to_refine`.

### `/runs/new`

Create a local task.

The form accepts these modes:

- `Validate`: measures the current prompt and persists the result as run of an iteration.
- `Optimize`: Runs the normal optimization loop.
- `Compare`: performs an iteration per item in `comparison_models`.

For `prompt`, `benchmark` and `config`, the screen accepts local path or pasted content. If the
content is filled in, it takes precedence over the specified path.

The `config` field is a complete YAML editor. It covers parameters such as models, budgets,
threshold, `output_format`, split train/val/test, rate limits, judge/embedding, provider cache,
model comparison and multi-objective.

### `/tasks/{task_id}`

Show task status:

- `queued`;
- `running`;
- `cancel_request`;
- `completed`;
- `failed`;
- `cancelled`.

While the task is active, the page automatically updates. When finished, opens link to the generated
run.

### `/runs/{run_id}/diff`

Shows a unified diff from `v0` to `best` by default.

Optional Query Params:

- `from_version`
- `to_version`

### `/runs/{run_id}/iterations/{version}/verdicts`

Show verdicts of a filtered iteration:

- `case_id`
- `passed`
- `regression`
- `tag`
- `assertion_type`
- `min_score`
- `max_score`

Each verdict can be expanded to see input, expected output, actual output and `assertion_detail`.

### `/runs/{run_id}/regressions`

Shows verdicts marked as regression.

### `/compare`

Compare two runs:

```text
/compare?left=<run-a>&right=<run-b>
```

## Dashboard JSON Endpoints

They are read-only endpoints useful for local scripts:

- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/verdicts`
- `GET /api/runs/{run_id}/verdicts?version=1`

## Scope

The dashboard is not multi-tenant and has no authentication. It is intended for local inspection or
trusted internal network use.

When you provide local paths in the form, the dashboard process reads these files in the filesystem
of the machine where `crucible serve` is running. Do not expose the dashboard on public network.
