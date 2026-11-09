# Operations

## Local State

Crucible writes in `.crucible/` by default:

```text
.crucible/
  crucible.sqlite
  cache/
  reports/
  runs/
```

Do not commit `.crucible/` unless you intend to version run artifacts.

## Cleaning

Manual cleaning:

```bash
rm -rf .crucible/cache
rm -rf .crucible/reports
```

Remove `.crucible/crucible.sqlite` only if you want to delete the indexed run history.

## Secrets

Use environment variables:

```bash
export CRUCIBLE_OPENAI_API_KEY=...
export CRUCIBLE_ANTHROPIC_API_KEY=...
export CRUCIBLE_GOOGLE_API_KEY=...
export CRUCIBLE_OPENROUTER_API_KEY=...
```

Avoid saving API keys in `config.yaml`.

## Cost Control

Always configure:

```yaml
max_cost_usd: 5.0
max_iterations: 5
max_wallclock_seconds: 1800
```

Run:

```bash
uv run crucible estimate-cost --config config.yaml
```

before expensive runs.

## Rate Limits

For local GPU providers:

```yaml
rate_limit:
  max_concurrent: 1
```

For cloud providers:

```yaml
rate_limit:
  max_concurrent: 4
  requests_per_minute: 60
  retry_attempts: 2
  retry_backoff_seconds: 0.5
```

## Use in CI

Typical flow:

```bash
uv sync
uv run crucible validate --prompt prompt.txt --benchmark benchmark.yaml --config config.yaml
uv run crucible report --run latest --format html
```

Save `.crucible/reports/*.html` as a CI artifact.

In CI, prefer deterministic assertions and fixed seeds when the provider supports them.

## Security

Reports may contain:

- prompts;
- user inputs;
- expected outputs;
- model outputs;
- judges rationales.

Do not publish reports if benchmarks have sensitive data.

## Exposing the API/Dashboard

`crucible serve` and `crucible api` are local-first. They do not implement auth.

Keep the bind address at `127.0.0.1`, except on a trusted network:

```bash
uv run crucible serve --host 127.0.0.1
uv run crucible api --host 127.0.0.1
```

## Troubleshooting

Provider does not connect:

- check API keys;
- check local server URL;
- run `validate` before `optimize`;
- reduce `rate_limit.max_concurrent`.

Unstable scores:

- configure `n_runs_per_case: 3`;
- check out `assertion_detail["runs"]["unstable"]`;
- reduce temperature;
- configure seed when supported.

Score high with many cases failing:

- check for assertions with partial score such as `field_by_field`;
- compare `global_score` with `pass_rate`;
- if a critical key dominates the decision, document it with `field_by_field.weights`;
- remember that field weights affect the case score, but do not create key-separated threshold in
  `config.yaml`.

Overfitting:

- enable `use_benchmark_split`;
- Inspect `validation_scores`;
- add more diverse cases;
- do not copy test examples for the prompt.

If `validation_scores.train` is far above `validation_scores.val`, the prompt is probably
specialized in the cases used for refining. If `val` and `test` get close, there is a better sign of
generalization.

As the current split is deterministic by `case.id`, review the distribution of cases. IDs grouped by
class, date or source can generate biased train/val/test.
