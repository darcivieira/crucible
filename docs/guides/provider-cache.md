# Guia: Cache Do Provider

Use cache remoto quando o input dos casos e grande ou quando o mesmo contexto sera
reutilizado em validacao, comparacao de modelos ou otimizacao. O objetivo e reduzir
custo e, em alguns providers, caber melhor no limite de contexto.

## Configurar

```yaml
provider_cache:
  enabled: true
  ttl_seconds: 3600
  cache_inputs: true
  on_error: fallback
  openai_retention: 24h
```

O Crucible cria cache por `case.input` antes da iteracao quando o provider suporta
cache explicito. Durante a chamada do target, o prompt renderizado informa que o
input esta no contexto cacheado.

## Google/Gemini

Gemini usa cache explicito:

```yaml
target_model:
  provider: google
  model_id: gemini-2.0-flash
  role: target
  cost_per_million_input_tokens_usd: 0.10
  cost_per_million_cached_input_tokens_usd: 0.025
  cost_per_million_output_tokens_usd: 0.40
```

A run registra `provider_cache_id` por verdict e soma `cached_tokens` quando o
provider devolve a metrica.

## OpenAI

OpenAI usa prompt caching automatico. O Crucible nao cria um cache ID manual. Quando
`provider_cache.enabled` esta ativo, ele adiciona `prompt_cache_key` e, se
configurado, `prompt_cache_retention` nos parametros. Se a API reportar tokens
cacheados, a run registra `cached_tokens_in`.

## Erros De Cache

```yaml
provider_cache:
  on_error: fail
```

Use `fail` quando o cache e requisito operacional. Use `fallback` quando e aceitavel
rodar sem cache e apenas registrar o warning na run.

## Custo

Declare a tarifa de input cacheado:

```yaml
cost_per_million_cached_input_tokens_usd: 0.025
```

Se esse campo ficar em `0.0`, o Crucible usa o preco normal de input para evitar
subestimar custo.
