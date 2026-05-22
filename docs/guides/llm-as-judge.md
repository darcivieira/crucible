# Guia: LLM-as-Judge

Use LLM-as-judge quando a resposta correta é subjetiva demais para `contains`,
`regex` ou comparação JSON.

## Quando Usar

- Resumos.
- Análise de risco.
- Respostas com justificativa.
- Tarefas em que existem múltiplas respostas aceitáveis.

Evite LLM-as-judge quando uma assertion determinística resolve. Ele é mais lento,
mais caro e precisa de rubrica clara.

## Gabarito

```yaml
assertion:
  type: llm_judge
  rubric: >
    A resposta deve identificar corretamente o risco, justificar com evidencias do
    input e nao inventar fatos.
  pass_threshold: 0.75
  position_swap: true
```

`position_swap` avalia expected/actual em duas ordens para reduzir viés de posição.

## Config

```yaml
judge_models:
  - provider: openai
    model_id: gpt-5
    role: judge
```

Se `judge_models` não for configurado, Crucible usa o `reasoning_model`.

## O Que Esperar

- O score vira parcial, de `0.0` a `1.0`.
- O report inclui payloads dos judges.
- Custo sobe, porque cada avaliação chama um modelo judge.
- Use poucos casos primeiro e aumente quando a rubrica estiver estável.
