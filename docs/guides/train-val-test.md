# Guia: Otimização Com Train/Val/Test

Use split quando você vai otimizar repetidamente e quer reduzir overfitting ao
gabarito.

## Por Que Usar

Sem split, o prompt pode melhorar no conjunto de casos usado para refinamento, mas
piorar em casos não vistos. Isso é especialmente comum quando o gabarito é grande e
o reasoning model recebe exemplos de falhas para reescrever o prompt.

Com split:

- `train`: usado para otimizar.
- `val`: mede se o melhor prompt encontrado generaliza para casos que não guiaram a
  otimização.
- `test`: mede resultado final em um conjunto segurado.

Na prática, o `optimize` deixa de usar o gabarito inteiro para aprender. Ele otimiza
no `train`, escolhe o melhor prompt dessa etapa e só então roda validações separadas
em `val` e `test`.

## Config

```yaml
use_gabarito_split: true
train_ratio: 0.7
val_ratio: 0.15
```

Com 1000 casos e essa configuração:

```text
train: 700 casos
val:   150 casos
test:  150 casos
```

O split é determinístico por `case.id`, então repetir a run mantém a divisão. Isso é
bom para comparação entre execuções, mas exige cuidado: se os IDs estiverem agrupados
por classe, tribunal, data ou tipo de caso, o split pode ficar enviesado.

Exemplo ruim:

```text
publicacao-00001..00300 = Prazo
publicacao-00301..00600 = Audiência
publicacao-00601..01000 = Nenhum
```

Nesse caso, o `train` pode ver uma distribuição diferente do `val`/`test`. Antes de
usar split em produção, embaralhe ou intercale os casos no gabarito, mantendo IDs
estáveis.

## Comando

```bash
uv run crucible optimize --config examples/train-val-test/config.yaml
```

Também é possível materializar os arquivos de split:

```bash
uv run crucible split-gabarito \
  --gabarito gabarito.yaml \
  --output-dir ./splits \
  --train 0.7 \
  --val 0.15
```

Isso cria gabaritos separados para inspeção, CI ou execução manual. O `optimize` com
`use_gabarito_split: true` não precisa desses arquivos: ele faz o split em memória.

## O Que Esperar

Ao final, a run registra:

- `validation_scores.train`
- `validation_scores.val`
- `validation_scores.test`
- `validation_scores.train_val_gap`

Interpretação:

- `train` alto e `val` baixo: o prompt provavelmente está overfitando aos exemplos de
  treino.
- `train` baixo e `val` baixo: o prompt ainda não aprendeu o comportamento esperado.
- `train`, `val` e `test` próximos: o prompt tende a generalizar melhor.
- `test` deve ser olhado como métrica final, não como fonte de exemplos para novo
  prompt.

## Quando Não Usar

Evite split quando o gabarito é muito pequeno. O Crucible exige pelo menos 3 casos,
mas isso é apenas o mínimo técnico. Na prática, use split quando cada conjunto ainda
tiver diversidade suficiente para representar o problema.

Para depuração inicial de provider, schema e assertion, rode `validate` ou `optimize`
sem split em um subconjunto pequeno. Depois habilite split para medir generalização.
