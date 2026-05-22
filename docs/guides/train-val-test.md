# Guia: Otimização Com Train/Val/Test

Use split quando você vai otimizar repetidamente e quer reduzir overfitting ao
gabarito.

## Por Que Usar

Sem split, o prompt pode melhorar no conjunto de casos usado para refinamento, mas
piorar em casos não vistos. Com split:

- `train`: usado para otimizar.
- `val`: mede generalização durante a seleção do melhor prompt.
- `test`: mede resultado final em casos segurados.

## Config

```yaml
use_gabarito_split: true
train_ratio: 0.7
val_ratio: 0.15
```

O split é determinístico por `case.id`, então repetir a run mantém a divisão.

## Comando

```bash
uv run crucible optimize --config examples/train-val-test/config.yaml
```

## O Que Esperar

Ao final, a run registra:

- `validation_scores.train`
- `validation_scores.val`
- `validation_scores.test`
- `validation_scores.train_val_gap`

Se o gap train/val for alto, o prompt provavelmente está overfitando.
