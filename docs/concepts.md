# Conceitos

## Prompt

Template versionado que será renderizado para cada caso do gabarito.

```text
Responda de forma objetiva.

Input:
{input}
```

O placeholder mais comum é `{input}`. O hash do conteúdo identifica versões em
relatórios, cache e diffs.

## Gabarito

Coleção versionada de casos de teste. Ele representa o contrato empírico que o
prompt precisa cumprir.

```yaml
name: sample
version: v1
cases:
  - id: case-001
    input: "Diga apenas: ok"
    expected_output: "ok"
    assertion:
      type: contains
```

## TestCase

Um caso individual com:

- `id`: identificador estável.
- `input`: entrada renderizada no prompt.
- `expected_output`: resposta esperada, schema ou referência.
- `assertion`: regra de avaliação.
- `weight`: peso no score global.
- `tags`: agrupadores para breakdown de score.

`weight` é peso do caso inteiro. Para pesar chaves dentro de um JSON estruturado,
use `assertion.weights` em `field_by_field`, não `weight`.

Quando o output do modelo é estruturado, `expected_output` pode ser o payload esperado:

```yaml
expected_output: |
  {'classification': 'Prazo', 'text_validation': 'Intime-se no prazo de 5 dias.'}
assertion:
  type: json_schema
```

Se o `config.yaml` declara `target_model.output_format.type: json_schema`, o Crucible
usa o schema do config para validar expected/actual e compara os campos parseados.
Isso permite usar gabaritos gerados automaticamente sem reescrever cada assertion.

Quando alguma chave é mais importante que outra, escreva a assertion explicitamente:

```yaml
expected_output: |
  {"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

## Assertion

Regra que compara `expected_output` com o output real do modelo. Assertions podem ser
determinísticas, estruturais, semânticas ou baseadas em LLM-as-judge.

Use a assertion mais barata que represente o requisito.

## TargetModel

Modelo cujo comportamento você quer melhorar com o prompt. Ele roda muitas vezes,
então custo, latência e rate limit importam.

## ReasoningModel

Modelo usado para diagnosticar falhas e propor o próximo prompt. Ele roda menos vezes,
mas costuma ser mais forte e mais caro.

## JudgeModel

Modelo opcional usado por assertions `llm_judge`. Se não for informado, o caminho
padrão usa o modelo de raciocínio como judge.

## OptimizationRun

Agregado que guarda uma execução completa:

- prompt inicial;
- config;
- gabarito;
- iterações;
- melhor iteração;
- motivo de parada;
- scores de validação quando split está habilitado.

Quando `use_gabarito_split` está habilitado, a run otimiza usando apenas o split de
treino. Depois que escolhe o melhor prompt, valida esse prompt nos splits de `val` e
`test` e grava os resultados em `validation_scores`.

## Iteration

Uma volta do loop:

1. renderiza prompt;
2. executa casos;
3. avalia assertions;
4. agrega score;
5. opcionalmente refina o prompt.

`v0` é o prompt original.

## Verdict

Resultado de um caso em uma iteração:

- score;
- pass/fail;
- output do modelo;
- latência;
- tokens;
- custo;
- detalhe da assertion;
- marcação de regressão.

## Best-Ever

A run retorna o melhor prompt já visto, não necessariamente o último prompt gerado.
Isso evita perder qualidade quando uma iteração posterior regride.

## Estado Local

`.crucible/` é parte do produto:

- SQLite para consulta;
- arquivos para auditoria humana;
- relatórios para compartilhamento;
- cache para evitar chamadas repetidas.

Use `/tmp` só para experimentos descartáveis.
