# Referência CLI

Todos os comandos são executados com:

```bash
uv run crucible <comando>
```

## `init`

Cria um projeto inicial.

```bash
uv run crucible init ./my-project
```

Arquivos criados:

- `prompt.txt`
- `gabarito.yaml`
- `config.yaml`

## `validate`

Executa o prompt atual contra o gabarito sem refinamento.

Use `validate` quando você quer responder:

- meu `prompt.txt` renderiza corretamente?
- meu `gabarito.yaml` está bem formado?
- as assertions estão avaliando o que eu espero?
- o `target_model` está acessível?
- qual score o prompt atual faz antes de otimizar?

```bash
uv run crucible validate \
  --prompt prompt.txt \
  --gabarito gabarito.yaml \
  --config config.yaml
```

O comando roda uma única iteração, equivalente à `v0` de uma otimização. Ele:

1. renderiza o prompt para cada caso;
2. chama o `target_model`;
3. aplica a assertion do caso;
4. calcula score, pass rate, custo, tokens e latência;
5. imprime uma tabela no terminal.

Ele não chama o `reasoning_model` para criar um novo prompt. Por isso é o comando
certo para depurar setup antes de gastar com `optimize`.

## `optimize`

Executa o loop completo de otimização.

Use `optimize` quando o setup já foi validado e você quer que o Crucible tente
melhorar o prompt automaticamente. Diferente de `validate`, esse comando usa o
`reasoning_model` para diagnosticar falhas e propor novas versões do prompt.

```bash
uv run crucible optimize --config config.yaml
```

Por padrão, `prompt.txt` e `gabarito.yaml` são carregados ao lado do `config.yaml`.

Com caminhos explícitos:

```bash
uv run crucible optimize \
  --config config.yaml \
  --prompt prompt_v0.txt \
  --gabarito regression.yaml
```

O comando:

1. executa o prompt inicial;
2. calcula score e métricas operacionais;
3. constrói um contrato da tarefa a partir do prompt inicial, config e gabarito;
4. seleciona falhas relevantes;
5. pede um diagnóstico ao `reasoning_model`;
6. pede uma proposta de novo prompt;
7. valida a proposta contra o contrato da tarefa;
8. se a proposta violar o contrato, pede reparos ao `reasoning_model` sem executar
   o target de novo;
9. executa a nova versão contra o gabarito somente quando o refino é válido;
10. repete até algum critério de parada.

O contrato da tarefa protege requisitos que não devem mudar durante a otimização.
Exemplo: se o prompt ou o gabarito indicam que um campo deve conter o trecho literal
que justifica uma classificação, o refino não pode trocar isso por uma justificativa
inferida como "o texto contém prazo". Nesses casos, o gabarito é usado como fonte da
verdade quando o prompt inicial é omisso.

Se o `reasoning_model` gerar um prompt inválido, o Crucible não cria uma nova
iteração com o mesmo prompt. Ele envia as violações de volta ao reasoning e pede uma
nova proposta, até `max_refinement_repair_attempts`. Se nenhuma tentativa produzir
um prompt válido, a run encerra com `reasoning_failed_to_refine`.

Critérios de parada:

- `threshold_reached`: melhor score atingiu o threshold;
- `max_iterations`: limite de iterações;
- `budget_exhausted`: custo máximo atingido;
- `time_exhausted`: tempo máximo atingido;
- `plateau`: score parou de melhorar;
- `no_failures`: não há falhas para refinar;
- `cancelled`: task cancelada pela API;
- `reasoning_failed_to_refine`: o modelo reasoning não conseguiu gerar uma proposta
  de prompt que preservasse o contrato da tarefa.

Ao terminar, a run fica salva em `.crucible/` e o melhor prompt pode ser visto com
`show-run`, `report`, `diff`, `export` ou pelo dashboard.

## `estimate-cost`

Estima custo antes da execução.

```bash
uv run crucible estimate-cost --config config.yaml
```

Com caminhos explícitos:

```bash
uv run crucible estimate-cost \
  --config config.yaml \
  --prompt prompt.txt \
  --gabarito gabarito.yaml
```

## `list-runs`

Lista runs recentes a partir do SQLite.

```bash
uv run crucible list-runs
uv run crucible list-runs --limit 50
```

## `show-run`

Mostra um resumo JSON da run.

```bash
uv run crucible show-run --run latest
uv run crucible show-run --run <run-id>
```

## `diff`

Mostra diff entre versões de prompt.

```bash
uv run crucible diff --run latest --from 0 --to best
uv run crucible diff --run <run-id> --from 1 --to 3
```

## `compare-runs`

Compara duas runs.

```bash
uv run crucible compare-runs <run-a> <run-b>
```

## `report`

Gera relatório.

```bash
uv run crucible report --run latest --format html
uv run crucible report --run latest --format json
uv run crucible report --run latest --format pdf
```

Os arquivos são escritos em `.crucible/reports/`.

## `export`

Exporta artefatos da run.

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible export --run latest --format parquet --output ./verdicts.parquet
uv run crucible export --run latest --format pdf --output ./report.pdf
```

## `split-gabarito`

Cria arquivos determinísticos de train/val/test para inspeção ou execução manual.

```bash
uv run crucible split-gabarito \
  --gabarito gabarito.yaml \
  --output-dir ./splits \
  --train 0.7 \
  --val 0.15
```

Esse comando materializa a mesma regra usada por `use_gabarito_split: true`: os casos
são ordenados por `case.id`, depois cortados em train, val e test. Com 1000 casos,
`--train 0.7 --val 0.15` gera 700/150/150.

Use o comando quando quiser revisar a divisão, versionar splits explícitos ou rodar
validações separadas em CI. Para o fluxo normal de `optimize`, basta habilitar
`use_gabarito_split` no config.

## `import-gabarito`

Converte formatos externos para o gabarito do Crucible.

```bash
uv run crucible import-gabarito --source jsonl --input cases.jsonl --output gabarito.yaml
uv run crucible import-gabarito --source promptfoo --input promptfoo.yaml --output gabarito.yaml
uv run crucible import-gabarito --source langsmith --input examples.json --output gabarito.yaml
uv run crucible import-gabarito --source dspy --input examples.json --output gabarito.yaml
```

## `serve`

Sobe o dashboard local.

```bash
uv run crucible serve
uv run crucible serve --host 0.0.0.0 --port 7777
```

URL padrão:

```text
http://127.0.0.1:7777
```

## `api`

Sobe a REST API local.

```bash
uv run crucible api --port 7788
```

O host padrão usa `CRUCIBLE_DASHBOARD_HOST` ou `127.0.0.1`.
