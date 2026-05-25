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
