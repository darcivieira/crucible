# Guia: Prompt Simples

Use este cenário quando você já tem um prompt em texto livre e quer medir se ele
responde bem a casos conhecidos.

## Quando Usar

- Você está criando um prompt novo.
- A saída esperada é texto simples.
- As validações podem ser determinísticas, como `contains`, `exact_match` ou `regex`.
- Você quer saber se vale a pena otimizar antes de gastar com reasoning model.

## Arquivos

`prompt.txt`:

```text
Classifique a mensagem do cliente e responda de forma objetiva.

Mensagem:
{input}
```

`gabarito.yaml`:

```yaml
name: support-triage
version: v1
cases:
  - id: billing-001
    input: "Fui cobrado duas vezes este mes."
    expected_output: "billing"
    assertion:
      type: contains
    tags: [billing]
```

## Fluxo

Primeiro valide:

```bash
uv run crucible validate --prompt prompt.txt --gabarito gabarito.yaml --config config.yaml
```

O `validate` responde se o prompt atual já passa no gabarito. Se falhar, olhe os
casos, ajuste assertions ou melhore o prompt manualmente.

Depois estime custo:

```bash
uv run crucible estimate-cost --config config.yaml
```

Só então rode:

```bash
uv run crucible optimize --config config.yaml
```

## O Que Esperar

- `v0` mostra o desempenho do prompt original.
- Versões posteriores mostram tentativas de melhoria.
- O melhor prompt é preservado mesmo se a última iteração piorar.
- Reports mostram tags e casos que ainda falham.
