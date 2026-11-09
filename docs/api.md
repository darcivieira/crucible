# REST API

Start the API:

```bash
uv run crucible api --port 7788
```

Base URL:

```text
http://127.0.0.1:7788
```

The API is intentionally thin. It uses the same `Optimizer`, SQLite store and reporting generator as
CLI.

Test whether the API is responding:

```bash
curl -s http://127.0.0.1:7788/runs
```

## Create Run

```http
POST /runs
Content-Type: application/json
```

Example with `curl` for simple validation:

```bash
curl -s -X POST http://127.0.0.1:7788/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "validate",
    "prompt": {
      "template": "Respond with only: {input}",
      "variables": ["input"]
    },
    "benchmark": {
      "name": "sample",
      "version": "v1",
      "cases": [
        {
          "id": "case-001",
          "input": "ok",
          "expected_output": "ok",
          "assertion": {"type": "contains"}
        }
      ]
    },
    "config": {
      "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
      "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"}
    }
  }'
```

Body:

```json
{
  "mode": "optimize",
  "prompt": {
    "template": "Respond: {input}",
    "variables": ["input"],
    "metadata": {}
  },
  "benchmark": {
    "name": "sample",
    "version": "v1",
    "cases": [
      {
        "id": "case-001",
        "input": "Say only ok",
        "expected_output": "ok",
        "assertion": {"type": "contains"},
        "weight": 1.0,
        "tags": ["smoke"]
      }
    ]
  },
  "config": {
    "threshold": 95.0,
    "max_iterations": 1,
    "max_cost_usd": 5.0,
    "target_model": {
      "provider": "fake",
      "model_id": "target",
      "role": "target"
    },
    "reasoning_model": {
      "provider": "fake",
      "model_id": "reasoning",
      "role": "reasoning"
    }
  }
}
```

`mode` is optional. Accepted values:

- `optimize`: Runs the optimization loop and creates a normal run.
- `validate`: runs only the current version of the prompt and persists a run with one iteration,
  `run_mode="validate"` and `stop_reason="validation_only"`.
- `compare`: performs an iteration per item of `comparison_models`.

For `validate`, `optimize` and `estimate-cost`, `config.target_model` and `config.reasoning_model`
are required. For `compare`, they may be absent; in this case, provide only
`comparison_models`.

Response:

```json
{
  "task_id": "abc123",
  "status": "queued"
}
```

## Consult Task Status

```http
GET /tasks/{task_id}
```

With `curl`:

```bash
curl -s http://127.0.0.1:7788/tasks/<task-id>
```

Possible responses:

```json
{"status": "queued"}
```

```json
{"status": "running"}
```

```json
{"status": "completed", "run_id": "...", "cancel_requested": false}
```

```json
{"status": "failed", "error": "..."}
```

The task status is persisted in SQLite in `api_tasks`, so restarting the API does not lose the task
history.

## Cancel Task

```http
POST /tasks/{task_id}/cancel
```

With `curl`:

```bash
curl -s -X POST http://127.0.0.1:7788/tasks/<task-id>/cancel
```

Mark `cancel_requested=true`. The optimizer observes this state between iterations and before
executing new cases. Provider calls already in progress are not interrupted by force.

## List Runs

```http
GET /runs
```

Returns summaries from the runs.

With `curl`:

```bash
curl -s http://127.0.0.1:7788/runs
```

## Get Run

```http
GET /runs/{run_id}
```

Returns the full serialized `OptimizationRun`.

With `curl`:

```bash
curl -s http://127.0.0.1:7788/runs/<run-id>
```

## Create Report

```http
POST /runs/{run_id}/reports/{format}
```

Formats:

- `json`
- `html`
- `pdf`

Response:

```json
{"path": ".crucible/reports/<run-id>.html"}
```

With `curl`:

```bash
curl -s -X POST http://127.0.0.1:7788/runs/<run-id>/reports/html
```

## Create Model Comparison

In `mode: compare`, `target_model` and `reasoning_model` may be missing. Provide candidates in
`comparison_models`:

```bash
curl -s -X POST http://127.0.0.1:7788/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "compare",
    "prompt": {
      "template": "Respond with only: {input}",
      "variables": ["input"]
    },
    "benchmark": {
      "name": "compare-sample",
      "version": "v1",
      "cases": [
        {
          "id": "case-001",
          "input": "ok",
          "expected_output": "ok",
          "assertion": {"type": "contains"}
        }
      ]
    },
    "config": {
      "comparison_models": [
        {
          "label": "fake-a",
          "model": {"provider": "fake", "model_id": "target-a", "role": "target"}
        },
        {
          "label": "fake-b",
          "model": {"provider": "fake", "model_id": "target-b", "role": "target"}
        }
      ]
    }
  }'
```

## Operational Notes

- There's no authentication yet.
- Background execution uses `FastAPI BackgroundTasks`.
- For multiuser use or production, add authentication before exposing the API.
