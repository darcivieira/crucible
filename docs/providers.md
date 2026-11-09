# Providers

Providers implement `ModelProvider.complete(prompt, params)`.

Configured Providers:

- `ollama`
- `openai`
- `anthropic`
- `google`
- `openrouter`
- `vllm`
- `llamacpp`
- `fake`

## Common ModelSpec

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

Environment variable:

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

Recommended for local target models. Keep concurrency low when the model uses a single GPU.

Ollama also receives `output_format`:

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

To `json_object`, the adapter sends `format: json`. To `json_schema`, it sends the schema in
`format`.

## OpenAI-Compatible APIs

`openai`, `openrouter` and `vllm` use payload in chat completions style.

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

To use the OpenAI Responses API, configure `api_mode: responses`:

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

In this mode, the adapter sends the schema in `text.format`. In `api_mode: chat_completions`, it
sends in `response_format`.

### Prompt Caching In OpenAI

When `provider_cache.enabled` is active, the OpenAI adapter receives extra parameters to instrument
prompt caching:

```yaml
provider_cache:
  enabled: true
  openai_retention: 24h
```

OpenAI does not display a manual `cache_id` like Google. The cache is automatic from the provider.
Crucible sends `prompt_cache_key` and, when configured, `prompt_cache_retention: 24h` in
`params.extra`; then records `cached_tokens_in` if the response brings cached tokens in the usage
block.

Use `cost_per_million_cached_input_tokens_usd` for the report to calculate cost with the cached
input tariff:

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

The adapter uses the format of the Messages API.

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

### Context Cache in Gemini

Google/Gemini has explicit cache. With `provider_cache.enabled`, Crucible creates a `cachedContents`
by `case.input` before iteration and passes this cache on target calls.

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

In the execution, the prompt sent to the model replaces `{input}` with an indication that the
content is in the cached context of the provider. The actual input is in the remote cache. Run
records `provider_cache_id` by verdict and `cached_tokens` when Google returns
`cachedContentTokenCount`.

Use `on_error: fail` when cache is required for cost or context limit. Use `on_error: fallback` when
you prefer to complete run even if the provider denies cache, for example by permission, billing or
incompatible model.

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

The current adapter calls `/completion`.

## Fake Provider

Used in tests and demos:

```yaml
target_model:
  provider: fake
  model_id: target
  role: target
```

The default fake provider echoes the prompt. Tests can inject a custom response.

## Embeddings

`embedding_similarity` uses `embedding_model` when configured:

```yaml
embedding_model:
  provider: openai
  model_id: text-embedding-3-small
  role: embedding
```

Available embedding providers:

- `fake`: deterministic embedding per hash for testing.
- `openai`: `/v1/embeddings`.
- `openrouter`: `/v1/embeddings` when supported by the model.
- `vllm`: `/v1/embeddings`, when the server displays the endpoint.
- `ollama`: `/api/embeddings`.

## Retries and Rate Limits

The HTTP provider retries these responses:

- `429`
- `500`
- `502`
- `503`
- `504`

Backoff:

```text
retry_backoff_seconds * 2 ** attempt
```

Concurrency and requests per minute are applied by `RateLimitedProvider`.

## Add Provider

1. Create an adapter in `src/crucible/modules/optimizer/adapters/providers/`.
2. Implement `payload()` and `parse()` if you can inherit from `HttpProvider`.
3. Or implement `complete()` directly.
4. Register it with `ModelProviderFactory`.
5. Add payload, parsing and error tests.
