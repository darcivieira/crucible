# Configuration

`config.yaml` maps directly to `OptimizationConfig`.

## Complete Example

```yaml
threshold: 95.0
max_iterations: 5
max_cost_usd: 5.0
max_wallclock_seconds: 1800
plateau_window: 3
plateau_min_delta: 0.5
parallelism: 4
n_runs_per_case: 1
max_failures_for_refinement: 10
max_refinement_repair_attempts: 5
instability_std_threshold_ms: 250.0

use_benchmark_split: false
train_ratio: 0.7
val_ratio: 0.15

execution_backend: local
distributed_workers: 4
selection_strategy: quality
objective_quality_weight: 1.0
objective_cost_weight: 0.0
objective_latency_weight: 0.0
active_learning_suggestions: 0
provider_cache:
  enabled: false
  ttl_seconds: 3600
  cache_inputs: true
  on_error: fail
  openai_retention: in_memory
comparison_models: []
comparison_value_quality_weight: 0.8
comparison_value_cost_weight: 0.2
comparison_value_latency_weight: 0.0

target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target
  api_mode: chat_completions
  params:
    temperature: 0.0
    max_tokens: 1024
    top_p: null
    seed: null
    extra: {}
  rate_limit:
    max_concurrent: 1
    requests_per_minute: null
    retry_attempts: 2
    retry_backoff_seconds: 0.5
  cost_per_million_input_tokens_usd: 0.0
  cost_per_million_cached_input_tokens_usd: 0.0
  cost_per_million_output_tokens_usd: 0.0
  context_window: 8192
  supports_json_mode: false
  supports_tool_use: false
  output_format:
    type: text

reasoning_model:
  provider: openai
  model_id: gpt-5
  role: reasoning
  params:
    temperature: 0.0
    max_tokens: 2048

judge_model: null
judge_models: []
embedding_model: null
```

## Optimization Fields

| Field | Meaning |
| --- | --- |
| `threshold` | Stops when the best score reaches this value. `0-100` scale. |
| `max_iterations` | Maximum number of iterations. Includes `v0`. |
| `max_cost_usd` | Maximum tracked cost budget. |
| `max_wallclock_seconds` | Real-time budget. |
| `plateau_window` | Recent score window used to detect Plateau. |
| `plateau_min_delta` | Minimum movement considered relevant. |
| `parallelism` | Global concurrency per case within an iteration. |
| `n_runs_per_case` | Repeat each case and choose the majority output. |
| `max_failures_for_refinement` | Maximum number of failures sent to the refiner. |
| `max_refinement_repair_attempts` | Maximum number of proposals that `reasoning_model` can try to generate for the same iteration before the run stops with `reasoning_failed_to_refine`. Includes the initial proposal and repairs. |
| `instability_std_threshold_ms` | Latency deviation used to mark instability. |
| `selection_strategy` | `quality` or `multi_objective`. |
| `active_learning_suggestions` | Number of suggestions for new cases at the end of the run. |
| `provider_cache` | Set remote caching of the provider when supported. |
| `comparison_models` | List of target models for `compare-models` or Dashboard/API `compare` mode. |
| `comparison_value_quality_weight` | Quality weight in the value for money ranking between models. |
| `comparison_value_cost_weight` | Cost weight in the value for money ranking between models. |
| `comparison_value_latency_weight` | Latency weight in the value for money ranking between models. |

## Refinement Repair

During `optimize`, `reasoning_model` is not free to change the contract of the task. After
evaluating an iteration, Crucible asks for a new prompt proposal and validates this proposal against
the inferred contract of the initial prompt, `config.yaml` and benchmark.

If the proposal violates the contract, Crucible does not execute `target_model` again with the same
prompt. Instead, it opens a repair subloop: it sends `reasoning_model` the rejected proposal, the
concrete violations and the contract that must be preserved. This avoids spending target calls on
repeated iterations.

```yaml
max_refinement_repair_attempts: 5
```

This limit counts the total of proposals for the same refining attempt: the initial proposal plus
repairs. With `5`, the reasoning model has up to five chances of producing a valid `new_prompt`. If
all
fail, the run ends with:

```text
stop_reason: reasoning_failed_to_refine
```

Use this signal to review the reasoning model, the initial prompt, or benchmark. It usually
appears when the reasoning model insists on removing a critical rule, exchanging literal extraction
for
inferred explanation, omiting `{input}` or repeating the same prompt.

## Reasoning Session

During `optimize`, each run creates a local reasoning session. It is not shared with other tasks and
does not depend on the provider's native memory. Crucible records each diagnosis, refinement
proposal, and repair, including the prompt sent to the reasoning model, raw response, parsed
payload, violations, and errors.

In the next calls of the same run, the optimizer injects a compact summary of this history into the
`reasoning_model` prompt. This helps the model remember what it has already tried, what proposals
have been rejected, and what violations should not repeat.

The full history is saved on the run payload in `reasoning_session`. This is useful for auditing by
SDK/API/dashboard and to understand why a refinement was accepted or rejected. There is no
mandatory configuration to enable this feature: it is automatic in `optimize` and is not used in
`validate` or `compare`.

## Global Threshold and Metrics By Field

`threshold` is applied to the overall run score:

```yaml
threshold: 95.0
```

It currently does not configure separate thresholds for JSON keys. For structured responses where
one key is
more important than another, set weights in benchmark assertion:

```yaml
expected_output: |
  {"classification": "Deadline", "text_validation": "Serve notice within 5 days."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

Thus, the `classification` field represents 95% of the score of that case. The global score remains
the weighted average of the cases.

Do not place key weights on `config.yaml`; they belong to the benchmark because they are part of the
evaluation rule of each case. `config.yaml` controls run, providers, budgets and global stop
criteria. Benchmark controls what is considered right or wrong.

In this version, there is also no configuration like:

```yaml
# Not implemented
field_metrics:
  classification:
    threshold: 95.0
```

To highlight a critical key today, use `field_by_field.weights`, domain tags in cases, and analysis
of verdicts/exports when you need an aggregated metric by key.

## Train/Val/Test

```yaml
use_benchmark_split: true
train_ratio: 0.7
val_ratio: 0.15
```

When enabled:

- Optimization uses train;
- the best prompt is validated in val and test;
- the scores are stored in `run.validation_scores`.

Use this when there is a risk of overfitting in the benchmark. Split is done in memory during
`optimize`; it is not necessary to create separate files.

The current behavior is deterministic:

1. orders cases by `case.id`;
2. separates `train_ratio` for training;
3. separates `val_ratio` for validation;
4. Use the rest as a test.

With `train_ratio: 0.7` and `val_ratio: 0.15`, a benchmark of 1000 cases gets 700 train cases, 150
val cases and 150 test cases.

This division is reproducible, but it can be biased if IDs group examples by type. If the benchmark
is sorted by class, source, or date, shuffle the cases before using the split.

## Execution Backend

```yaml
execution_backend: local
distributed_workers: 4
```

Available values:

- `local`: direct execution with `asyncio.gather`.
- `distributed`: local asynchronous pool limited by `distributed_workers`.
- `ray`: optional backend using Ray.
- `dask`: optional backend using Dask Distributed.

Ray/Dask are optional extras:

```bash
uv sync --extra distributed
```

## Multi-Objective Optimization

```yaml
selection_strategy: multi_objective
objective_quality_weight: 1.0
objective_cost_weight: 0.2
objective_latency_weight: 0.1
```

When `selection_strategy` is `multi_objective`, `best_iteration` uses `objective_score`, and the run
records `pareto_frontier_versions`.

## Model Comparison

`comparison_models` defines the targets evaluated by the `compare-models` command, the API with
`mode: compare` and the dashboard in `Compare` mode.

In this mode, `target_model` and `reasoning_model` are not required. They remain mandatory for
`validate`, `optimize` and `estimate-cost`, because these streams need a main target and a standard
reasoning/judge model.

```yaml
comparison_models:
  - label: gemini-flash
    model:
      provider: google
      model_id: gemini-2.0-flash
      role: target
      params:
        temperature: 0.0
        max_tokens: 1024
      cost_per_million_input_tokens_usd: 0.10
      cost_per_million_output_tokens_usd: 0.40
  - label: gpt-mini
    model:
      provider: openai
      model_id: gpt-5-mini
      role: target
      api_mode: responses
      params:
        temperature: 0.0
        max_tokens: 1024
      cost_per_million_input_tokens_usd: 0.25
      cost_per_million_cached_input_tokens_usd: 0.025
      cost_per_million_output_tokens_usd: 2.00
```

Each item runs a single iteration with the same prompt and the same benchmark. The resulting run
shows:

- score and pass rate per model;
- total cost and p95 latency per model;
- cached input tokens, when the provider reports this metric;
- global winner by quality;
- Global winner at lower cost;
- overall value for money winner;
- winners per case.

The value for money ranking normalizes quality, cost and latency within the comparison itself.
Adjust
the weights when you want to favor price or time:

```yaml
comparison_value_quality_weight: 0.7
comparison_value_cost_weight: 0.3
comparison_value_latency_weight: 0.0
```

With the weights above, quality still dominates, but cost explicitly breaks ties. If all the
weights are zero, the ranking again uses only quality.

## Remote Provider Cache

`provider_cache` enables provider cache capabilities to reduce cost when the same context is reused.

```yaml
provider_cache:
  enabled: true
  ttl_seconds: 3600
  cache_inputs: true
  on_error: fallback
  openai_retention: 24h
```

Use when inputs are large, when you run multiple repeated models/cases or when you are comparing
prompts against the same material. Crucible prepares the cached context before performing iteration
and records `cached_tokens` in metrics when the provider returns this information.

Fields:

- `enabled`: enables the behavior.
- `ttl_seconds`: lifespan requested for explicit caches used by Google.
- `cache_inputs`: creates cache by `case.input`.
- `on_error`: `fail` aborts if the remote cache fails; `fallback` continues without cache and
  registers warning on run.
- `openai_retention`: `in_memory` or `24h`, used only as instrumentation for OpenAI.

Today there are two different behaviors:

- Google/Gemini uses explicit input cache. Crucible creates `cachedContents` and passes `cache_id`
  on the following calls.
- OpenAI uses automatic prompt caching. There is no equivalent manual ID cache in the current
  stream; Crucible adds `prompt_cache_key`/retention in parameters when enabled and records
  `cached_tokens_in` when API reports cached tokens.

For cache cost, also state:

```yaml
target_model:
  cost_per_million_input_tokens_usd: 1.00
  cost_per_million_cached_input_tokens_usd: 0.10
  cost_per_million_output_tokens_usd: 4.00
```

If `cost_per_million_cached_input_tokens_usd` stays in `0.0`, Crucible uses the normal input price
for cached tokens. This avoids underestimating cost by accident when you have not yet reported the
correct price of the provider.

## Active Learning

```yaml
active_learning_suggestions: 10
```

At the end of the run, Crucible suggests cases for benchmark expansion based on failures,
regressions, and unstable outputs.

## ModelSpec

```yaml
provider: openai
model_id: gpt-5
role: reasoning
api_mode: chat_completions
params:
  temperature: 0.0
  max_tokens: 2048
  top_p: null
  seed: null
  extra: {}
rate_limit:
  max_concurrent: 4
  requests_per_minute: 60
  retry_attempts: 2
  retry_backoff_seconds: 0.5
cost_per_million_input_tokens_usd: 1.25
cost_per_million_cached_input_tokens_usd: 0.125
cost_per_million_output_tokens_usd: 10.0
context_window: 128000
supports_json_mode: true
supports_tool_use: false
output_format:
  type: json_schema
  name: summary_output
  strict: true
  schema:
    type: object
    additionalProperties: false
    required: [summary]
    properties:
      summary:
        type: string
```

## Output Format

`output_format` describes the output contract requested from the provider. It is different from the
prompt: the prompt guides the model; the output format goes on the API payload when the provider
supports structured output.

Values:

- `text`: Free response, default.
- `json_object`: requests valid JSON without ensuring specific schema.
- `json_schema`: Requests adherence to a JSON Schema.

Example with OpenAI Responses API:

```yaml
target_model:
  provider: openai
  model_id: gpt-5-mini
  role: target
  api_mode: responses
  output_format:
    type: json_schema
    name: summary_output
    strict: true
    schema:
      type: object
      additionalProperties: false
      required: [summary, risk]
      properties:
        summary:
          type: string
        risk:
          type: string
          enum: [low, medium, high]
```

In the OpenAI adapter with `api_mode: responses`, this is sent as `text.format`. In Chat Completions
mode and OpenAI-compatible providers, it is sent as `response_format`. In Ollama, it becomes
`format`.

Use `output_format` along with a structural assertion in the benchmark, e.g. `json_schema` or
`field_by_field`. The first requests the output format from the model; the assertion measures
whether the result
has fulfilled the contract.

When benchmark brings an expected payload, but assertion came as `json_schema`, Crucible uses
`target_model.output_format` schema as a comparative basis:

```yaml
target_model:
  output_format:
    type: json_schema
    schema:
      type: object
      required: [classification, text_validation]
      properties:
        classification:
          type: string
        text_validation:
          type: string
```

```yaml
expected_output: |
  {'classification': 'Deadline', 'text_validation': 'Serve notice within 5 days.'}
assertion:
  type: json_schema
```

In this stream, `expected_output` and actual output are parsed, both are validated against config
schema and then compared field by field. This is useful for automatically generated benchmarks. For
manually written benchmarks, `field_by_field` makes the intention clearer and allows weights per
field.

See full examples in `examples/structured-output/`.

## Roles

- `target`: model that is being optimized.
- `reasoning`: model that diagnoses and refines.
- `judge`: model used by assertions LLM-as-judge.
- `embedding`: model used by `embedding_similarity`.

## Embedding Model

```yaml
embedding_model:
  provider: openai
  model_id: text-embedding-3-small
  role: embedding
```

When configured, CLI/SDK passes this provider to assertions `embedding_similarity`.

## Providers

- `ollama`
- `openai`
- `anthropic`
- `google`
- `openrouter`
- `vllm`
- `llamacpp`
- `fake`

## Environment Variables

Settings use the `CRUCIBLE_` prefix:

```bash
CRUCIBLE_OPENAI_API_KEY=...
CRUCIBLE_ANTHROPIC_API_KEY=...
CRUCIBLE_GOOGLE_API_KEY=...
CRUCIBLE_OPENROUTER_API_KEY=...
CRUCIBLE_OLLAMA_URL=http://localhost:11434
CRUCIBLE_VLLM_URL=http://localhost:8000/v1
CRUCIBLE_LLAMACPP_URL=http://localhost:8080
CRUCIBLE_SQLITE_PATH=.crucible/crucible.sqlite
CRUCIBLE_RUNS_DIR=.crucible/runs
CRUCIBLE_REPORTS_DIR=.crucible/reports
CRUCIBLE_CACHE_DIR=.crucible/cache
CRUCIBLE_PLUGIN_MODULES=my_project.crucible_plugin
```

## Cost Estimate

Cost tracking depends on:

- `cost_per_million_input_tokens_usd`
- `cost_per_million_cached_input_tokens_usd`
- `cost_per_million_output_tokens_usd`

Local providers have zero cost by default. Cloud providers also stay at zero cost until you declare
prices in config.

## Compatibility with Existing Projects

English names are the documented defaults. Existing projects can continue using
legacy SDK imports and keyword arguments, CLI flags/commands, benchmark filenames,
API input fields, and split configuration keys. Existing JSON and SQLite run
payloads are normalized when loaded; reading them does not rewrite user data.
The legacy hash and split-setting keys remain available in serialized output.

When both field names are present in configuration or input JSON, the English
field takes precedence. The CLI resolves current and legacy benchmark filenames
without duplicating files. Existing VSCode benchmark-path settings are honored
unless an explicit English setting overrides them.

Project-authored interface text and internal prompts are English. User tasks and
expected labels are preserved in their original language; constraint matching
continues to recognize English and Portuguese. Historical rule-source values are
normalized to the current English value when loaded.
