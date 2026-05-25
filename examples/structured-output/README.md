# Saida Estruturada

Este exemplo mostra tres formas de testar uma resposta estruturada.

## 1. Payload Esperado Com `json_schema`

Use `gabarito.yaml` quando o gabarito vem de um pipeline que ja preenche o
`expected_output` com a resposta esperada:

```yaml
expected_output: |
  {'summary': 'pagamento em atraso com promessa de quitacao em 7 dias', 'risk': 'medium'}
assertion:
  type: json_schema
```

Como o `config.*.yaml` declara `target_model.output_format.type: json_schema`, o
Crucible usa o schema do config para validar expected/actual e compara os campos
parseados. Isso cobre respostas recebidas como string contendo JSON ou literal
similar a Python.

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## 2. Schema Como Gabarito

Use `gabarito.schema.yaml` quando voce quer validar apenas se o output respeita o
contrato estrutural:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.schema.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## 3. Comparacao Explicita Campo A Campo

Use `gabarito.field-by-field.yaml` quando voce controla o gabarito manualmente e quer
deixar a intencao clara:

```yaml
assertion:
  type: field_by_field
  weights:
    risk: 95
    summary: 5
```

Nesse exemplo, `risk` domina o score do caso. Em um classificador, o mesmo padrao
poderia ser `classification: 95` e `text_validation: 5`.

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.field-by-field.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## Ollama

Troque o config por `config.ollama.yaml` para executar o mesmo fluxo com Ollama:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.yaml \
  --config ./examples/structured-output/config.ollama.yaml
```
