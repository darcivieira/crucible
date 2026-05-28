# Gabaritos E Assertions

## Formato Do Gabarito

```yaml
name: extraction-v1
version: "1.0"
description: Casos para extrair valores de contratos.
cases:
  - id: case-001
    input: |
      Extraia o CNPJ:
      ACME LTDA, CNPJ 12.345.678/0001-90.
    expected_output: "12.345.678/0001-90"
    assertion:
      type: exact_match
      normalize: true
    weight: 1.0
    tags: [extraction, cnpj]
    metadata:
      source: synthetic
```

## Campos Do TestCase

| Campo | Obrigatório | Significado |
| --- | --- | --- |
| `id` | sim | Identificador estável usado em reports e regressões. |
| `input` | sim | Entrada renderizada em `{input}`. |
| `expected_output` | sim | Resposta esperada, schema ou texto de referência. |
| `assertion` | sim | Configuração da regra de avaliação. |
| `weight` | não | Peso do caso. Padrão `1.0`. |
| `tags` | não | Agrupadores para breakdown de score. |
| `metadata` | não | Metadados livres. |

## Como Escolher Assertion

Prefira a opção mais barata que capture o requisito:

1. determinística;
2. estrutural;
3. semântica;
4. LLM-as-judge.

LLM-as-judge é útil, mas custa mais, é mais lento e precisa de calibração.

## Assertions Determinísticas

### `exact_match`

```yaml
assertion:
  type: exact_match
  normalize: true
  case_sensitive: true
```

Use para IDs, labels, valores estritos e strings normalizadas.

### `contains`

```yaml
assertion:
  type: contains
  case_sensitive: false
```

Usa `expected_output` como substring.

### `regex`

```yaml
assertion:
  type: regex
  pattern: "\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}"
```

Se `pattern` for omitido, `expected_output` é usado como regex.

### `numeric_match`

```yaml
assertion:
  type: numeric_match
  tolerance: 0.01
```

Use para valores monetários, contagens e cálculos.

### `json_equal`

```yaml
expected_output: '{"status":"ok"}'
assertion:
  type: json_equal
```

Compara estruturas JSON parseadas.

Use quando o valor inteiro retornado pelo modelo precisa ser igual ao JSON esperado.
O Crucible tenta parsear JSON válido, JSON dentro de blocos Markdown e literais simples
com aspas simples, mas JSON válido com aspas duplas continua sendo o formato recomendado.

### `json_schema`

```yaml
expected_output: |
  {"type":"object","required":["status"]}
assertion:
  type: json_schema
```

Também é possível declarar o schema inline:

```yaml
assertion:
  type: json_schema
  schema:
    type: object
    required: [status]
```

`json_schema` aqui é uma assertion: ela valida o output depois que o modelo responde.
Para também pedir que o provider force a saída estruturada na chamada do modelo, use
`target_model.output_format` em `config.yaml`.

Não use `json_schema` quando `expected_output` for o payload esperado:

```yaml
expected_output: '{"status":"ok","risk":"low"}'
assertion:
  type: field_by_field
```

Nesse caso use `json_equal` para igualdade completa ou `field_by_field` para comparar
campo a campo com score parcial.

Existe uma exceção pragmática: quando `target_model.output_format.type` está como
`json_schema` no `config.yaml`, mas o gabarito gerado veio com `assertion.type:
json_schema` e `expected_output` contém o payload esperado, o Crucible usa o schema
do `config.yaml` para validar os dois lados e compara os campos parseados. Isso
existe para suportar gabaritos vindos de pipelines externos, mas em gabaritos
escritos manualmente prefira `field_by_field` ou `json_equal`.

Exemplo típico vindo de YAML gerado:

```yaml
expected_output: |
  {'classification': 'Prazo', 'text_validation': 'Intime-se no prazo de 5 dias.'}
assertion:
  type: json_schema
```

Com `target_model.output_format.type: json_schema`, isso não é tratado como schema
inline. O valor é tratado como payload esperado, passa por parse junto com o output
real e é comparado campo a campo.

Quando houver textos longos, aspas ou dois-pontos no conteúdo, prefira bloco literal
YAML com `|` para evitar erro de sintaxe no arquivo:

```yaml
expected_output: |
  {'classification': 'Prazo', 'text_validation': 'Junte o documento: comprovante atualizado.'}
```

## Assertions Estruturais

### `field_by_field`

```yaml
expected_output: '{"status":"ok","risk":"low"}'
assertion:
  type: field_by_field
  weights:
    status: 2.0
    risk: 1.0
```

Compara campos de objetos JSON e retorna score parcial.
É a opção mais prática quando o modelo retorna uma string contendo JSON e o gabarito
descreve os campos esperados, como classificação, status, risco ou justificativa.
O Crucible faz parse dos dois lados antes de comparar, então funciona mesmo quando
o provider devolve uma string contendo JSON em vez de um objeto já materializado.

#### Pesos Por Campo

Use `weights` quando nem todas as chaves têm a mesma importância. Em extrações
estruturadas, é comum a classe/label ser mais importante que um texto auxiliar:

```yaml
expected_output: |
  {"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

Os pesos são proporcionais. O exemplo acima é equivalente a `0.95` e `0.05`. Se o
modelo acertar `classification` e errar `text_validation`, o caso recebe score `0.95`.
Se errar `classification` e acertar `text_validation`, recebe `0.05`.

Campos não listados em `weights` recebem peso `1.0`. Use pesos positivos e evite
configurações ambíguas como todos os campos com peso `0`. O campo só é considerado
correto quando o valor parseado é igual ao valor esperado; se o campo estiver ausente
no output real, ele conta como erro.

O `passed` do caso continua sendo estrito: em `field_by_field`, uma resposta parcial
normalmente recebe score parcial, mas só passa quando todos os campos esperados batem.
Por isso é possível ter `global_score` subindo enquanto o `pass_rate` segue baixo.

#### Assertions Por Campo

Por padrão, todo campo em `field_by_field` usa comparação exata. Isso preserva
compatibilidade com gabaritos antigos:

```yaml
assertion:
  type: field_by_field
```

equivale a:

```yaml
assertion:
  type: field_by_field
  field_assertions:
    classification:
      type: exact
    text_validation:
      type: exact
```

Quando um campo fechado deve ser avaliado de forma quantitativa e outro campo aberto
precisa de avaliação qualitativa, configure `field_assertions`:

```yaml
expected_output: |
  {"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
  field_assertions:
    classification:
      type: exact
    text_validation:
      type: llm_judge
      threshold: 0.8
      rubric: >
        Verifique se o trecho extraído está presente no input original e se é
        semanticamente equivalente ao valor esperado. Penalize inferências,
        paráfrases inventadas ou trechos que não existam no texto fonte.
```

Tipos disponíveis por campo:

- `exact`: igualdade exata do valor parseado.
- `normalized_exact`: compara texto normalizando espaços; por padrão ignora caixa.
- `contains`: aceita quando expected contém actual ou actual contém expected.
- `embedding_similarity`: compara o campo por similaridade de embeddings.
- `llm_judge`: usa judge com rubrica específica do campo.

Para `llm_judge`, o Crucible envia ao judge o valor esperado, o valor extraído e o
input original do caso. Isso permite avaliar se uma evidência textual realmente veio
do texto fonte, não apenas se parece semanticamente plausível.

Em `validate` e `optimize`, quando `judge_models` não é informado, o
`reasoning_model` pode servir como judge padrão. Em `compare`, `reasoning_model` não
é obrigatório; portanto, se algum `field_assertions.*.type` for `llm_judge`, configure
`judge_model` ou `judge_models` explicitamente.

Isso muda o score do caso, não cria uma métrica global separada por chave. Hoje o
threshold global do `config.yaml` continua avaliando o score agregado da run. Para
destacar o desempenho por campo nos reports, use tags complementares ou exporte os
verdicts para análise externa.

Se você precisa que `classification` represente 95% da decisão, prefira
`field_by_field.weights`. A exceção pragmática de `json_schema` com payload esperado
usa comparação campo a campo sem pesos; ela existe para gabaritos gerados
automaticamente, não para expressar prioridade entre chaves.

Durante `optimize`, esses exemplos estruturados também ajudam a montar o contrato da
tarefa. Se o gabarito mostra que `text_validation` deve conter um trecho literal, o
refiner não pode transformar esse campo em uma justificativa inferida. Se tentar, a
proposta é rejeitada e o `reasoning_model` recebe as violações para gerar outro
prompt, sem nova execução do target com o prompt antigo.

### `pydantic_model`

```yaml
assertion:
  type: pydantic_model
  schema:
    type: object
    required: [status]
```

Valida schema primeiro e depois compara campos.

## Assertion Semântica

### `embedding_similarity`

```yaml
assertion:
  type: embedding_similarity
  threshold: 0.85
```

Requer um embedding provider em `AssertionContext`. O caminho padrão da CLI ainda
não configura embedding provider automaticamente, então use via SDK ou estenda a
wiring de providers.

## LLM-as-Judge

### `llm_judge`

```yaml
assertion:
  type: llm_judge
  rubric: >
    A resposta deve identificar corretamente o risco e justificar com base no input.
  pass_threshold: 0.7
  position_swap: true
  calibration_examples:
    - expected: "alto risco"
      actual: "alto risco por inadimplencia"
      score: 0.9
```

Por padrão, `position_swap` avalia expected/actual nas duas ordens para reduzir viés
de posição. Se `judge_models` tiver múltiplos modelos, o score é a média e o
pass/fail usa consenso simples.

### `llm_judge_with_rationale`

Mesmo comportamento de `llm_judge`, com foco em retornar racional detalhado.

## Assertion Via Plugin

```yaml
assertion:
  type: plugin
  name: my_assertion
  config:
    threshold: 3
```

Veja [Plugins](plugins.md).

## Tags E Pesos

Use tags para tornar reports acionáveis:

```yaml
tags: [extraction, cnpj, formatted]
weight: 2.0
```

Boas tags geralmente representam:

- família da tarefa;
- conceito de domínio;
- dificuldade;
- formato de saída.

## Gabarito Como Fonte Da Verdade No Optimize

Durante `optimize`, o Crucible usa o gabarito também para construir o contrato da
tarefa. Esse contrato orienta o `reasoning_model` e impede que o prompt novo degrade
requisitos críticos.

Exemplo: se `expected_output` mostra que `text_validation` deve conter o trecho
literal que levou à classificação, o refino não deve transformar esse campo em uma
explicação inferida. A diferença é:

- correto: `"text_validation": "Intime-se no prazo de 5 dias."`
- incorreto: `"text_validation": "O texto contém uma intimação com prazo."`

Quando o prompt inicial não explicita esse detalhe, o padrão observado no gabarito é
tratado como fonte da verdade para o refino.

## Boas Práticas

- Mantenha `id` estável.
- Inclua casos simples, casos difíceis e edge cases.
- Use assertions determinísticas sempre que possível.
- Habilite train/val/test quando otimizar repetidamente sobre o mesmo gabarito.
- Não vaze exemplos de test set como few-shot no prompt.
- Mantenha expected outputs curtos e precisos, exceto em assertions semânticas.
