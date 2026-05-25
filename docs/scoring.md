# Scoring

O scoring do Crucible combina qualidade da resposta com métricas operacionais. A
qualidade é calculada por caso de teste; custo, latência e tokens são agregados junto
com o score para deixar trade-offs explícitos.

## Unidade Básica

Cada `Verdict` contém:

- `score`: valor entre `0.0` e `1.0`.
- `passed`: booleano definido pela assertion.
- `test_case.weight`: peso do caso no score global.
- `execution`: latência, tokens, custo e output do modelo.
- `assertion_detail`: detalhes específicos da assertion.

O score global da iteração é uma média ponderada em escala `0-100`.

```text
global_score = sum(score * weight) / sum(weight) * 100
```

## Pass Rate Versus Score

`pass_rate` e `global_score` não são a mesma coisa.

- `pass_rate`: percentual de casos com `passed=true`.
- `global_score`: média ponderada dos scores, incluindo scores parciais.

Isso permite que assertions como `field_by_field`, `embedding_similarity` e
`llm_judge` expressem progresso parcial sem transformar tudo em binário.

## Breakdown Por Tag

Tags ajudam a responder onde o prompt está falhando.

```yaml
tags: [extraction, cnpj, formatted]
weight: 2.0
```

O relatório calcula score por tag usando os casos que possuem aquela tag. Se um caso
tem múltiplas tags, ele contribui para todos os grupos correspondentes.

Use tags para:

- tipo de tarefa;
- entidade de domínio;
- formato de saída;
- nível de dificuldade;
- origem do caso.

## Breakdown Por Tipo De Assertion

`by_assertion_type` mostra score agregado por tipo de validação:

- `exact_match`
- `contains`
- `regex`
- `numeric_match`
- `json_equal`
- `json_schema`
- `field_by_field`
- `pydantic_model`
- `embedding_similarity`
- `llm_judge`
- `llm_judge_with_rationale`
- `plugin`

Esse breakdown é útil para diferenciar falha de formato, falha estrutural e falha
semântica.

## Output Format Versus Assertion

Quando o usuário configura `target_model.output_format`, o Crucible passa um contrato
de saída para o provider. Isso pode fazer o modelo menor ou SLM responder em JSON ou
aderir a um schema antes mesmo da avaliação.

A assertion continua necessária. Ela é a medição empírica do contrato:

- `output_format`: solicita/força formato na chamada ao modelo.
- `json_schema`: valida contrato estrutural; se `expected_output` for um payload e
  houver schema em `target_model.output_format`, valida expected/actual contra esse
  schema e compara campos.
- `json_equal`: compara estruturas parseadas por igualdade total.
- `field_by_field`: compara campos de objetos parseados e permite score parcial.

Essa separação importa porque nem todo provider garante schema com a mesma força, e
alguns modelos podem ignorar parcialmente o contrato.

Em todos os casos estruturais, o Crucible tenta parsear strings comuns retornadas por
LLMs: JSON válido, JSON dentro de blocos Markdown e literais simples com aspas
simples. JSON válido com aspas duplas continua sendo o formato recomendado para
gabaritos versionados.

## Worst Cases

`worst_case_ids` mantém até 10 casos com menor score na iteração. Esses casos são
úteis para:

- priorizar investigação humana;
- alimentar diagnóstico do reasoning model;
- identificar regressões;
- selecionar novos exemplos de treino ou validação.

## Métricas Operacionais

Cada `ScoreReport` também inclui:

- `total_cost_usd`;
- `p50_latency_ms`;
- `p95_latency_ms`;
- `total_tokens`.

Essas métricas são calculadas a partir das execuções dos casos. Elas não alteram o
score de qualidade hoje, mas aparecem em CLI, dashboard, reports e exports.

## Regressões

Um verdict pode ser marcado como `is_regression` quando um caso que passava deixa de
passar em uma iteração posterior. A run ainda retorna o melhor prompt visto, mas a
marcação de regressão ajuda a entender mudanças ruins causadas por refinamento.

## Repetição Por Caso

Quando `n_runs_per_case > 1`, o mesmo caso é executado várias vezes. O Crucible usa
majority vote para escolher o output representativo e registra detalhes em
`assertion_detail["runs"]`, incluindo:

- quantidade de runs;
- distribuição de outputs;
- output vencedor;
- desvio de latência;
- flag `unstable`.

Use isso quando o provider for não determinístico mesmo com temperatura baixa.

## Interpretação Recomendada

- Score alto com custo alto pode não ser aceitável para produção.
- Pass rate alto com score baixo indica casos parciais falhando.
- Score por tag baixo indica lacuna específica de prompt.
- P95 alto indica risco operacional mesmo com qualidade boa.
- Instabilidade em repeated runs sugere reduzir temperatura, fixar seed ou trocar
  provider/configuração.

## Pareto Frontier

Quando `selection_strategy: multi_objective`, cada iteração recebe `objective_score`.
O score combina qualidade com penalidade de custo e latência:

```text
objective = quality * quality_weight - cost_norm * cost_weight - latency_norm * latency_weight
```

A run também registra `pareto_frontier_versions`, contendo versões não dominadas por
outra iteração em qualidade, custo e p95 de latência.
