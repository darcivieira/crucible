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
max_refinement_repair_attempts: 5
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
| `max_refinement_repair_attempts` | Quantidade máxima de propostas que o `reasoning_model` pode tentar gerar para a mesma iteração antes da run parar com `reasoning_failed_to_refine`. Inclui a proposta inicial e os reparos. |
| `instability_std_threshold_ms` | Desvio de latência usado para marcar instabilidade. |
| `selection_strategy` | `quality` ou `multi_objective`. |
| `active_learning_suggestions` | Quantidade de sugestões de novos casos ao final da run. |
| `provider_cache` | Configura cache remoto do provider quando suportado. |
| `comparison_models` | Lista de modelos alvo para `compare-models` ou modo `compare` do dashboard/API. |
| `comparison_value_quality_weight` | Peso de qualidade no ranking de custo-benefício entre modelos. |
| `comparison_value_cost_weight` | Peso de custo no ranking de custo-benefício entre modelos. |
| `comparison_value_latency_weight` | Peso de latência no ranking de custo-benefício entre modelos. |

## Reparo De Refino

Durante `optimize`, o `reasoning_model` não tem liberdade para mudar o contrato da
tarefa. Depois de avaliar uma iteração, o Crucible pede uma proposta de novo prompt
e valida essa proposta contra o contrato inferido do prompt inicial, `config.yaml` e
gabarito.

Se a proposta violar o contrato, o Crucible não executa o `target_model` de novo com
o mesmo prompt. Em vez disso, ele abre um subloop de reparo: envia ao
`reasoning_model` a proposta rejeitada, as violações concretas e o contrato que deve
ser preservado. Isso evita gastar chamadas de target em iterações repetidas.

```yaml
max_refinement_repair_attempts: 5
```

Esse limite conta o total de propostas para uma mesma tentativa de refino: a proposta
inicial mais os reparos. Com `5`, o reasoning tem até cinco chances de produzir um
`new_prompt` válido. Se todas falharem, a run termina com:

```text
stop_reason: reasoning_failed_to_refine
```

Use esse sinal para revisar o modelo reasoning, o prompt inicial ou o gabarito. Ele
normalmente aparece quando o reasoning insiste em remover uma regra crítica, trocar
extração literal por explicação inferida, omitir `{input}` ou repetir o mesmo prompt.

## Threshold Global E Métricas Por Campo

`threshold` é aplicado ao score global da run:

```yaml
threshold: 95.0
```

Ele não configura, hoje, thresholds separados por chave de JSON. Para respostas
estruturadas em que uma chave é mais importante que outra, configure pesos na
assertion do gabarito:

```yaml
expected_output: |
  {"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

Assim, o campo `classification` representa 95% do score daquele caso. O score global
continua sendo a média ponderada dos casos.

Não coloque pesos de chave em `config.yaml`; eles pertencem ao gabarito porque fazem
parte da regra de avaliação de cada caso. O `config.yaml` controla a run, providers,
budgets e critérios globais de parada. O gabarito controla o que é considerado certo
ou errado.

Também não existe, nesta versão, uma configuração como:

```yaml
# Nao implementado
field_metrics:
  classification:
    threshold: 95.0
```

Para evidenciar uma chave crítica hoje, use `field_by_field.weights`, tags de domínio
nos casos e análise dos verdicts/exportações quando precisar de uma métrica agregada
por chave.

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

Use isso quando houver risco de overfitting no gabarito. O split é feito em memória
durante o `optimize`; não é necessário criar arquivos separados.

O comportamento atual é determinístico:

1. ordena os casos por `case.id`;
2. separa `train_ratio` para treino;
3. separa `val_ratio` para validação;
4. usa o restante como test.

Com `train_ratio: 0.7` e `val_ratio: 0.15`, um gabarito de 1000 casos fica com 700
casos de train, 150 de val e 150 de test.

Essa divisão é reprodutível, mas pode ser enviesada se os IDs agruparem exemplos por
tipo. Se o gabarito estiver ordenado por classe, origem ou data, intercale os casos
antes de usar split.

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

## Comparação De Modelos

`comparison_models` define os targets avaliados pelo comando `compare-models`, pela
API com `mode: compare` e pelo dashboard em modo `Compare`.

Nesse modo, `target_model` e `reasoning_model` não são obrigatórios. Eles continuam
obrigatórios para `validate`, `optimize` e `estimate-cost`, porque esses fluxos
precisam de um target principal e de um modelo de raciocínio/judge padrão.

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

Cada item roda uma única iteração com o mesmo prompt e o mesmo gabarito. A run
resultante mostra:

- score e pass rate por modelo;
- custo total e p95 de latência por modelo;
- tokens de entrada cacheados, quando o provider reporta essa métrica;
- vencedor global por qualidade;
- vencedor global por menor custo;
- vencedor global por custo-benefício;
- vencedores por caso.

O ranking de custo-benefício normaliza qualidade, custo e latência dentro da própria
comparação. Ajuste os pesos quando quiser privilegiar preço ou tempo:

```yaml
comparison_value_quality_weight: 0.7
comparison_value_cost_weight: 0.3
comparison_value_latency_weight: 0.0
```

Com os pesos acima, qualidade ainda domina, mas custo passa a desempatar de forma
explícita. Se todos os pesos forem zero, o ranking volta a usar apenas qualidade.

## Cache Remoto Do Provider

`provider_cache` habilita recursos de cache do provider para reduzir custo quando o
mesmo contexto é reutilizado.

```yaml
provider_cache:
  enabled: true
  ttl_seconds: 3600
  cache_inputs: true
  on_error: fallback
  openai_retention: 24h
```

Use quando os inputs são grandes, quando você roda vários modelos/casos repetidos ou
quando está comparando prompts sobre o mesmo material. O Crucible prepara o contexto
cacheado antes de executar a iteração e registra `cached_tokens` nas métricas quando
o provider devolve essa informação.

Campos:

- `enabled`: liga o comportamento.
- `ttl_seconds`: tempo de vida solicitado para caches explícitos, usado pelo Google.
- `cache_inputs`: cria cache por `case.input`.
- `on_error`: `fail` aborta se o cache remoto falhar; `fallback` segue sem cache e
  registra warning na run.
- `openai_retention`: `in_memory` ou `24h`, usado apenas como instrumentação para
  OpenAI.

Hoje existem dois comportamentos diferentes:

- Google/Gemini usa cache explícito por input. O Crucible cria `cachedContents` e
  passa o `cache_id` nas chamadas seguintes.
- OpenAI usa prompt caching automático. Não existe um cache ID manual equivalente no
  fluxo atual; o Crucible adiciona `prompt_cache_key`/retenção nos parâmetros quando
  habilitado e registra `cached_tokens_in` quando a API reporta tokens cacheados.

Para custo com cache, declare também:

```yaml
target_model:
  cost_per_million_input_tokens_usd: 1.00
  cost_per_million_cached_input_tokens_usd: 0.10
  cost_per_million_output_tokens_usd: 4.00
```

Se `cost_per_million_cached_input_tokens_usd` ficar em `0.0`, o Crucible usa o preço
normal de input para os tokens cacheados. Isso evita subestimar custo por acidente
quando você ainda não informou o preço correto do provider.

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

Quando o gabarito traz um payload esperado, mas a assertion veio como
`json_schema`, o Crucible usa o schema de `target_model.output_format` como base
comparativa:

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
  {'classification': 'Prazo', 'text_validation': 'Intime-se no prazo de 5 dias.'}
assertion:
  type: json_schema
```

Nesse fluxo, `expected_output` e output real são parseados, ambos são validados contra
o schema do config e depois comparados campo a campo. Isso é útil para gabaritos
gerados automaticamente. Para gabaritos escritos manualmente, `field_by_field` deixa
a intenção mais clara e permite pesos por campo.

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
- `cost_per_million_cached_input_tokens_usd`
- `cost_per_million_output_tokens_usd`

Providers locais têm custo zero por padrão. Providers cloud também ficam com custo
zero até você declarar preços no config.
