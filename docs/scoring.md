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

Existem dois níveis de peso que não devem ser confundidos:

- `test_case.weight`: muda quanto um caso inteiro pesa no score global.
- `field_by_field.weights`: muda quanto cada chave pesa dentro do score daquele caso.

## Pass Rate Versus Score

`pass_rate` e `global_score` não são a mesma coisa.

- `pass_rate`: percentual de casos com `passed=true`.
- `global_score`: média ponderada dos scores, incluindo scores parciais.

Isso permite que assertions como `field_by_field`, `embedding_similarity` e
`llm_judge` expressem progresso parcial sem transformar tudo em binário.

## Pesos Por Campo Em JSON

Quando a resposta é um objeto JSON, `field_by_field` pode atribuir pesos diferentes
para cada chave:

```yaml
expected_output: |
  {"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

O score do caso é calculado pela soma dos pesos acertados dividida pela soma total
dos pesos:

```text
case_score = matched_field_weight / total_field_weight
```

Nesse exemplo:

- acertou `classification` e errou `text_validation`: score `0.95`;
- errou `classification` e acertou `text_validation`: score `0.05`;
- acertou os dois campos: score `1.0`;
- errou os dois campos: score `0.0`.

Isso é útil quando uma chave é operacionalmente mais importante que outra. Em uma
classificação jurídica, por exemplo, `classification` pode valer 95% do caso e
`text_validation` apenas 5%.

Na prática:

- use `test_case.weight` quando um caso inteiro é mais importante que outro;
- use `field_by_field.weights` quando, dentro do mesmo JSON, uma chave é mais crítica;
- combine os dois apenas quando essa intenção estiver clara para quem vai revisar o
  relatório.

Limitação atual: esses pesos afetam o score do caso e, por consequência, o
`global_score`. O Crucible ainda não expõe uma métrica global nativa como
`classification_score` nem um threshold específico por chave no `config.yaml`.

Hoje, o threshold configurado aqui:

```yaml
threshold: 95.0
```

continua sendo aplicado ao score global da run. Para acompanhar uma chave específica,
use pesos por campo no gabarito e exporte os verdicts para análise externa, ou modele
casos/tags separados para essa dimensão.

Também há uma diferença importante entre score parcial e aprovação do caso. A
assertion `field_by_field` marca `passed=true` apenas quando todos os campos esperados
batem. Se `classification` vale 95% e `text_validation` vale 5%, acertar só
`classification` produz score `0.95`, mas o caso ainda aparece como falha parcial.
Isso é esperado: `global_score` mede progresso ponderado; `pass_rate` mede casos
totalmente resolvidos.

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
  schema e compara campos com peso uniforme.
- `json_equal`: compara estruturas parseadas por igualdade total.
- `field_by_field`: compara campos de objetos parseados e permite score parcial.

Se você quer prioridade por chave, use `field_by_field.weights`. O caminho
`json_schema` com payload esperado é uma compatibilidade para gabaritos gerados
automaticamente e não aplica pesos por campo.

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
