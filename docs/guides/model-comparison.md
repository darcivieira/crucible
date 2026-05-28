# Guia: Comparacao De Modelos

Use este fluxo quando a duvida principal nao e o prompt, mas o modelo alvo. Ele
responde: "qual modelo entrega melhor resultado neste gabarito, considerando custo e
latencia?"

## Quando Usar

- antes de rodar uma otimizacao longa;
- quando voce esta escolhendo entre SLM, LLM pequeno e modelo cloud;
- quando um modelo barato parece bom, mas voce precisa medir regressao por caso;
- quando custo de input grande pesa na decisao.

## Configurar

Declare os candidatos em `comparison_models`:

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

No modo de comparacao, `target_model` e `reasoning_model` nao sao obrigatorios. O
Crucible usa cada item de `comparison_models` como target temporario da iteracao.
Eles continuam obrigatorios apenas quando o mesmo arquivo tambem for usado para
`validate`, `optimize` ou `estimate-cost`.

## Executar

```bash
uv run crucible compare-models \
  --prompt prompt.txt \
  --gabarito gabarito.yaml \
  --config config.yaml
```

Tambem funciona pelo dashboard escolhendo `Compare` em `Nova run`, ou pela API com
`mode: compare`.

## O Que Esperar

A run gerada tem `run_mode: compare` e uma iteracao por modelo. O relatorio mostra:

- score e pass rate;
- custo total;
- p95 de latencia;
- tokens cacheados;
- melhor modelo por score;
- modelo mais barato;
- melhor custo-beneficio;
- vencedores por caso.

O vencedor por custo-beneficio usa pesos normalizados:

```yaml
comparison_value_quality_weight: 0.8
comparison_value_cost_weight: 0.2
comparison_value_latency_weight: 0.0
```

Se a qualidade for inegociavel, mantenha peso alto em qualidade. Se o objetivo for
triagem de alto volume, aumente o peso de custo.

## Proximo Passo

Depois de escolher o target, promova esse modelo para `target_model` e rode:

```bash
uv run crucible validate --config config.yaml
uv run crucible optimize --config config.yaml
```
