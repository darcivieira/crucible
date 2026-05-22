# Tutorial End-To-End: Triagem De Suporte

Este tutorial mostra um fluxo completo: escrever prompt, criar gabarito, validar,
otimizar, abrir report e exportar o melhor prompt.

## Cenário

Queremos classificar mensagens de suporte em categorias operacionais:

- `billing`
- `technical`
- `account`
- `cancellation`
- `other`

## Arquivos

Use o exemplo:

```text
examples/customer-support-triage/
  prompt.txt
  gabarito.yaml
  config.yaml
```

## 1. Validar

```bash
uv run crucible validate \
  --prompt examples/customer-support-triage/prompt.txt \
  --gabarito examples/customer-support-triage/gabarito.yaml \
  --config examples/customer-support-triage/config.yaml
```

Resultado esperado: uma tabela com a iteração `v0`, score, pass rate, custo e p95.

## 2. Estimar Custo

```bash
uv run crucible estimate-cost --config examples/customer-support-triage/config.yaml
```

Resultado esperado: JSON com estimativa de tokens e custo máximo aproximado.

## 3. Otimizar

```bash
uv run crucible optimize --config examples/customer-support-triage/config.yaml
```

Resultado esperado:

- histórico de iterações;
- run persistida em `.crucible/crucible.sqlite`;
- report HTML em `.crucible/reports/`;
- melhor prompt preservado.

## 4. Inspecionar

```bash
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible diff --run latest --from 0 --to best
uv run crucible report --run latest --format html
```

Abra também:

```bash
uv run crucible serve
```

## 5. Exportar

```bash
uv run crucible export --run latest --format prompt --output best_prompt.txt
uv run crucible export --run latest --format csv --output verdicts.csv
```

## Como Ler O Report

- Score global mostra qualidade agregada.
- Score por tag mostra categorias fracas.
- Worst cases indicam onde o prompt precisa de exemplos ou instrução mais clara.
- Regressões mostram casos que pioraram depois de uma mudança.

Um bom resultado não é apenas score alto. Verifique também custo, p95 de latência e
se o prompt final continua legível para manutenção.
