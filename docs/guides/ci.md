# Guia: Uso Em CI

Use Crucible no CI para impedir regressões de prompt antes de publicar mudanças.

## Estratégia Recomendada

No CI, prefira `validate`, não `optimize`.

`validate` é previsível: mede o prompt atual e falha rápido se provider/gabarito
quebrar. `optimize` pode consumir mais tempo e custo.

## Exemplo GitHub Actions

```yaml
name: Prompt Regression

on:
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: |
          uv run crucible validate \
            --prompt prompt.txt \
            --gabarito gabarito.yaml \
            --config config.yaml
      - run: uv run crucible report --run latest --format html
```

## O Que Guardar Como Artefato

- `.crucible/reports/*.html`
- exports CSV/Parquet se houver análise posterior

Não publique reports se o gabarito tiver dados sensíveis.
