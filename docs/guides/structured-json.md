# Guia: Saída JSON Estruturada

Use este cenário quando o contrato real do produto exige JSON em um formato específico.

## Ideia Central

Há duas camadas diferentes:

- `output_format`: pede ao provider para retornar JSON/schema.
- `json_schema` assertion: mede se o output realmente cumpriu o contrato.

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

No gabarito:

```yaml
assertion:
  type: json_schema
  schema:
    type: object
    required: [summary, risk]
```

## Comando

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## O Que Esperar

- Se o provider respeitar o schema, a assertion deve passar.
- Se o provider gerar JSON inválido, `json_schema` falha e o report mostra o erro.
- Se o schema mudar, o cache é invalidado automaticamente.
