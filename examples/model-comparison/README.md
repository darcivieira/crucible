# Model Comparison

Exemplo para escolher um modelo alvo antes de otimizar um prompt.

```bash
uv run crucible compare-models \
  --prompt examples/model-comparison/prompt.txt \
  --gabarito examples/model-comparison/gabarito.yaml \
  --config examples/model-comparison/config.yaml
```

O gabarito usa `field_by_field` com peso maior em `classification`, porque essa e a
decisao principal. `text_validation` ainda conta, mas como evidencia auxiliar.

Este config nao declara `target_model` nem `reasoning_model`, porque o modo de
comparacao usa apenas os targets listados em `comparison_models`.
