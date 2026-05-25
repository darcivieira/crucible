# Guia: Saída JSON Estruturada

Use este cenário quando o contrato real do produto exige JSON em um formato específico.

## Ideia Central

Há três responsabilidades diferentes:

- `output_format`: pede ao provider para retornar JSON/schema.
- `json_schema` assertion: mede se o output realmente cumpriu o contrato.
- `json_equal` ou `field_by_field`: mede se o payload retornado tem os valores esperados.

Não confie apenas no prompt para forçar JSON. Quando o provider suporta saída
estruturada, declare isso no `config.yaml`.

## Exemplo

```yaml
target_model:
  provider: openai
  model_id: gpt-5-mini
  role: target
  api_mode: responses
  output_format:
    type: json_schema
    name: summary_output
    strict: true
    schema:
      type: object
      additionalProperties: false
      required: [summary, risk]
      properties:
        summary:
          type: string
        risk:
          type: string
          enum: [low, medium, high]
```

### Validar Apenas O Contrato

```yaml
assertion:
  type: json_schema
  schema:
    type: object
    required: [summary, risk]
```

Esse formato valida se a resposta tem o shape esperado, mas não compara valores
específicos.

### Comparar Payload Esperado

```yaml
expected_output: '{"summary":"Cliente prometeu pagar em 7 dias.","risk":"low"}'
assertion:
  type: field_by_field
```

Esse formato compara os campos do payload retornado com os campos esperados.

Quando uma chave é mais importante que outra, use pesos:

```yaml
expected_output: |
  {"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
```

Aqui, `classification` domina o score do caso. Isso ajuda quando o produto precisa
priorizar a classe extraída e tratar texto auxiliar como sinal secundário.

O threshold continua global:

```yaml
threshold: 95.0
```

Esse valor não significa "classification precisa bater 95%". Ele significa "a run
para quando o score global chegar a 95". O peso `classification: 95` faz essa chave
representar 95% do score de cada caso onde ela aparece.

Exemplo de leitura:

- `classification` correta e `text_validation` errada: score do caso `0.95`;
- `classification` errada e `text_validation` correta: score do caso `0.05`;
- ambos corretos: score do caso `1.0`.

Mesmo com score parcial alto, o caso só fica com `passed=true` quando todos os campos
esperados batem. Use o `global_score` para ver progresso ponderado e o `pass_rate`
para ver quantos casos ficaram totalmente corretos.

### Gabarito Gerado Com `json_schema`

Quando um gabarito é gerado automaticamente e vem com `assertion.type: json_schema`,
mas o `expected_output` contém o payload esperado, o Crucible usa o schema declarado
em `target_model.output_format` para validar expected/actual e compara os campos
parseados:

```yaml
expected_output: |
  {'summary': 'pagamento em atraso com promessa de quitacao em 7 dias', 'risk': 'medium'}
assertion:
  type: json_schema
```

Mesmo que um modelo menor retorne uma string com JSON dentro, o Crucible faz parse
dos dois lados antes de comparar. Ainda assim, prefira escrever o gabarito como JSON
válido, com aspas duplas.

Esse modo de compatibilidade compara campos com peso uniforme. Se uma chave precisa
valer mais que outra, troque a assertion do caso para `field_by_field` e declare
`weights`.

## Comando

Payload esperado usando schema do config:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Validação apenas de contrato:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.schema.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Comparação explícita campo a campo:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.field-by-field.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## O Que Esperar

- Se o provider respeitar o schema, a assertion deve passar.
- Se o provider gerar JSON inválido, `json_schema` falha e o report mostra o erro.
- Se o retorno tiver JSON parseável com valores diferentes do gabarito, o contrato
  passa, mas a comparação de campos falha ou recebe score parcial.
- Se o schema mudar, o cache é invalidado automaticamente.
