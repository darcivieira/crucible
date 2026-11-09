# Guide: Provider Cache

Use remote cache when case input is large or when the same context will be reused in validation,
model comparison or optimization. The goal is to reduce cost and, in some providers, fit better in
context limit.

## Configure

```yaml
provider_cache:
  enabled: true
  ttl_seconds: 3600
  cache_inputs: true
  on_error: fallback
  openai_retention: 24h
```

Crucible creates `case.input` cache before iteration when the provider supports explicit cache.
During the target call, the rendered prompt informs that the input is in the cached context.

## Google/Gemini

Gemini uses explicit cache:

```yaml
target_model:
  provider: google
  model_id: gemini-2.0-flash
  role: target
  cost_per_million_input_tokens_usd: 0.10
  cost_per_million_cached_input_tokens_usd: 0.025
  cost_per_million_output_tokens_usd: 0.40
```

The run records `provider_cache_id` by verdict and adds `cached_tokens` when the provider returns
the counter.

## OpenAI

OpenAI uses automatic prompt caching. Crucible does not create a manual ID cache. When
`provider_cache.enabled` is active, it adds `prompt_cache_key` and, if configured,
`prompt_cache_retention` in the parameters. If the API reports cached tokens, the run records
`cached_tokens_in`.

## Cache Errors

```yaml
provider_cache:
  on_error: fail
```

Use `fail` when caching is an operational requirement. Use `fallback` when running without caching
is acceptable; a warning is recorded on the run.

## Cost

Declare the cached input tariff:

```yaml
cost_per_million_cached_input_tokens_usd: 0.025
```

If this field stays in `0.0`, Crucible uses the normal input price to avoid underestimating cost.
