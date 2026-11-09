# Model Comparison

Example to choose a target model before optimizing a prompt.

```bash
uv run crucible compare-models \
  --prompt examples/model-comparison/prompt.txt \
  --benchmark examples/model-comparison/benchmark.yaml \
  --config examples/model-comparison/config.yaml
```

The benchmark uses `field_by_field` with higher weight in `classification`, because this is the main
decision. `text_validation` still counts, but as an auxiliary evidence.

This config does not declare `target_model` or `reasoning_model`, because comparison mode only uses
the targets listed in `comparison_models`.
