# Providers

Providers implementam `ModelProvider.complete(prompt, params)`.

Providers configurados:

- `ollama`
- `openai`
- `anthropic`
- `google`
- `openrouter`
- `vllm`
- `llamacpp`
- `fake`

## ModelSpec Comum

```yaml
provider: openai
model_id: gpt-5
role: reasoning
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
cost_per_million_input_tokens_usd: 0.0
cost_per_million_cached_input_tokens_usd: 0.0
cost_per_million_output_tokens_usd: 0.0
```

## Ollama

Variável de ambiente:

```bash
CRUCIBLE_OLLAMA_URL=http://localhost:11434
```

Config:

```yaml
target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target
  params:
    temperature: 0.0
    max_tokens: 1024
  rate_limit:
    max_concurrent: 1
```

Recomendado para modelos alvo locais. Mantenha concorrência baixa quando o modelo
usa uma única GPU.

Ollama também recebe `output_format`:

```yaml
target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target
  output_format:
    type: json_schema
    schema:
      type: object
      required: [answer]
      properties:
        answer:
          type: string
```

Para `json_object`, o adapter envia `format: json`. Para `json_schema`, envia o
schema em `format`.

## APIs OpenAI-Compatible

`openai`, `openrouter` e `vllm` usam payload no estilo chat completions.

OpenAI:

```bash
CRUCIBLE_OPENAI_API_KEY=...
```

```yaml
reasoning_model:
  provider: openai
  model_id: gpt-5
  role: reasoning
```

Para usar a Responses API da OpenAI, configure `api_mode: responses`:

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
      required: [summary]
      properties:
        summary:
          type: string
```

Nesse modo, o adapter envia o schema em `text.format`. Em `api_mode:
chat_completions`, ele envia em `response_format`.

### Prompt Caching Na OpenAI

Quando `provider_cache.enabled` está ativo, o adapter OpenAI recebe parâmetros extras
para instrumentar prompt caching:

```yaml
provider_cache:
  enabled: true
  openai_retention: 24h
```

A OpenAI não expõe, nesse fluxo, um `cache_id` manual como o Google. O cache é
automático do provider. O Crucible envia `prompt_cache_key` e, quando configurado,
`prompt_cache_retention: 24h` em `params.extra`; depois registra
`cached_tokens_in` se a resposta trouxer tokens cacheados no bloco de usage.

Use `cost_per_million_cached_input_tokens_usd` para que o relatório calcule custo
com a tarifa de input cacheado:

```yaml
target_model:
  provider: openai
  model_id: gpt-5-mini
  role: target
  cost_per_million_input_tokens_usd: 0.25
  cost_per_million_cached_input_tokens_usd: 0.025
  cost_per_million_output_tokens_usd: 2.00
```

OpenRouter:

```bash
CRUCIBLE_OPENROUTER_API_KEY=...
```

```yaml
target_model:
  provider: openrouter
  model_id: google/gemini-flash-1.5
  role: target
```

vLLM:

```bash
CRUCIBLE_VLLM_URL=http://localhost:8000/v1
```

```yaml
target_model:
  provider: vllm
  model_id: meta-llama/Llama-3.1-8B-Instruct
  role: target
```

## Anthropic

```bash
CRUCIBLE_ANTHROPIC_API_KEY=...
```

```yaml
reasoning_model:
  provider: anthropic
  model_id: claude-sonnet-4-5
  role: reasoning
```

O adapter usa o formato da Messages API.

## Google

```bash
CRUCIBLE_GOOGLE_API_KEY=...
```

```yaml
reasoning_model:
  provider: google
  model_id: gemini-2.5-pro
  role: reasoning
```

### Context Cache No Gemini

O Google/Gemini tem cache explícito. Com `provider_cache.enabled`, o Crucible cria um
`cachedContents` por `case.input` antes da iteração e passa esse cache nas chamadas
do target.

```yaml
provider_cache:
  enabled: true
  ttl_seconds: 3600
  cache_inputs: true
  on_error: fallback

target_model:
  provider: google
  model_id: gemini-2.0-flash
  role: target
  cost_per_million_input_tokens_usd: 0.10
  cost_per_million_cached_input_tokens_usd: 0.025
  cost_per_million_output_tokens_usd: 0.40
```

Na execução, o prompt enviado ao modelo substitui `{input}` por uma indicação de que
o conteúdo está no contexto cacheado do provider. O input real fica no cache remoto.
A run registra `provider_cache_id` por verdict e `cached_tokens` quando o Google
retorna `cachedContentTokenCount`.

Use `on_error: fail` quando cache é obrigatório para custo ou limite de contexto. Use
`on_error: fallback` quando você prefere concluir a run mesmo que o provider negue o
cache, por exemplo por permissão, billing ou modelo incompatível.

## llama.cpp

```bash
CRUCIBLE_LLAMACPP_URL=http://localhost:8080
```

```yaml
target_model:
  provider: llamacpp
  model_id: local
  role: target
```

O adapter atual chama `/completion`.

## Fake Provider

Usado em testes e demos:

```yaml
target_model:
  provider: fake
  model_id: target
  role: target
```

O fake provider padrão ecoa o prompt. Testes podem injetar um responder customizado.

## Embeddings

`embedding_similarity` usa `embedding_model` quando configurado:

```yaml
embedding_model:
  provider: openai
  model_id: text-embedding-3-small
  role: embedding
```

Providers de embedding disponíveis:

- `fake`: embedding determinístico por hash para testes.
- `openai`: `/v1/embeddings`.
- `openrouter`: `/v1/embeddings`, quando suportado pelo modelo.
- `vllm`: `/v1/embeddings`, quando o servidor expõe o endpoint.
- `ollama`: `/api/embeddings`.

## Retry E Rate Limit

O provider HTTP faz retry para:

- `429`
- `500`
- `502`
- `503`
- `504`

Backoff:

```text
retry_backoff_seconds * 2 ** attempt
```

Concorrência e requests por minuto são aplicados por `RateLimitedProvider`.

## Adicionar Provider

1. Crie um adapter em `src/crucible/modules/optimizer/adapters/providers/`.
2. Implemente `payload()` e `parse()` se puder herdar de `HttpProvider`.
3. Ou implemente `complete()` diretamente.
4. Registre no `ModelProviderFactory`.
5. Adicione testes de payload, parsing e erro.
