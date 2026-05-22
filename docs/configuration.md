# Configuração

`config.yaml` mapeia diretamente para `OptimizationConfig`.

## Exemplo Completo

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
instability_std_threshold_ms: 250.0

use_gabarito_split: false
train_ratio: 0.7
val_ratio: 0.15

execution_backend: local
distributed_workers: 4
selection_strategy: quality
objective_quality_weight: 1.0
objective_cost_weight: 0.0
objective_latency_weight: 0.0
active_learning_suggestions: 0

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

## Campos De Otimização

| Campo | Significado |
| --- | --- |
| `threshold` | Para quando o melhor score atinge esse valor. Escala `0-100`. |
| `max_iterations` | Número máximo de iterações. Inclui `v0`. |
| `max_cost_usd` | Budget máximo de custo rastreado. |
| `max_wallclock_seconds` | Budget de tempo real. |
| `plateau_window` | Janela de scores recentes usada para detectar plateau. |
| `plateau_min_delta` | Movimento mínimo considerado relevante. |
| `parallelism` | Concorrência global por caso dentro de uma iteração. |
| `n_runs_per_case` | Repete cada caso e escolhe o output majoritário. |
| `max_failures_for_refinement` | Limite de falhas enviadas ao refiner. |
| `instability_std_threshold_ms` | Desvio de latência usado para marcar instabilidade. |
| `selection_strategy` | `quality` ou `multi_objective`. |
| `active_learning_suggestions` | Quantidade de sugestões de novos casos ao final da run. |

## Train/Val/Test

```yaml
use_gabarito_split: true
train_ratio: 0.7
val_ratio: 0.15
```

Quando habilitado:

- a otimização usa train;
- o melhor prompt é validado em val e test;
- os scores são guardados em `run.validation_scores`.

Use isso quando houver risco de overfitting no gabarito.

## Backend De Execução

```yaml
execution_backend: local
distributed_workers: 4
```

Valores disponíveis:

- `local`: execução direta com `asyncio.gather`.
- `distributed`: pool assíncrono local limitado por `distributed_workers`.
- `ray`: backend opcional usando Ray.
- `dask`: backend opcional usando Dask Distributed.

Ray/Dask são extras opcionais:

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

Quando `selection_strategy` é `multi_objective`, `best_iteration` usa
`objective_score`, e a run registra `pareto_frontier_versions`.

## Active Learning

```yaml
active_learning_suggestions: 10
```

Ao final da run, Crucible sugere casos para expansão do gabarito com base em falhas,
regressões e outputs instáveis.

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

`output_format` descreve o contrato de saída solicitado ao provider. Ele é diferente
do prompt: o prompt orienta o modelo; o output format vai no payload da API quando o
provider suporta saída estruturada.

Valores:

- `text`: resposta livre, padrão.
- `json_object`: pede JSON válido, sem garantir schema específico.
- `json_schema`: pede aderência a um JSON Schema.

Exemplo com OpenAI Responses API:

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

No adapter OpenAI com `api_mode: responses`, isso é enviado como `text.format`. No
modo Chat Completions e providers OpenAI-compatible, é enviado como
`response_format`. Em Ollama, vira `format`.

Use `output_format` junto com uma assertion estrutural no gabarito, por exemplo
`json_schema` ou `field_by_field`. O primeiro solicita o formato ao modelo; a
assertion mede se o resultado cumpriu o contrato.

Veja exemplos completos em `examples/structured-output/`.

## Papéis

- `target`: modelo que está sendo otimizado.
- `reasoning`: modelo que diagnostica e refina.
- `judge`: modelo usado por assertions LLM-as-judge.
- `embedding`: modelo usado por `embedding_similarity`.

## Embedding Model

```yaml
embedding_model:
  provider: openai
  model_id: text-embedding-3-small
  role: embedding
```

Quando configurado, a CLI/SDK passam esse provider para assertions
`embedding_similarity`.

## Providers

- `ollama`
- `openai`
- `anthropic`
- `google`
- `openrouter`
- `vllm`
- `llamacpp`
- `fake`

## Variáveis De Ambiente

Configurações usam o prefixo `CRUCIBLE_`:

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

## Estimativa De Custo

O tracking de custo depende de:

- `cost_per_million_input_tokens_usd`
- `cost_per_million_output_tokens_usd`

Providers locais têm custo zero por padrão. Providers cloud também ficam com custo
zero até você declarar preços no config.
