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
