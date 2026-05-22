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

## Boas Práticas

- Mantenha `id` estável.
- Inclua casos simples, casos difíceis e edge cases.
- Use assertions determinísticas sempre que possível.
- Habilite train/val/test quando otimizar repetidamente sobre o mesmo gabarito.
- Não vaze exemplos de test set como few-shot no prompt.
- Mantenha expected outputs curtos e precisos, exceto em assertions semânticas.
