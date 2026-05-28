# Dashboard

O dashboard é uma aplicação FastAPI local sobre `.crucible/crucible.sqlite`.

Suba com:

```bash
uv run crucible serve
```

URL padrão:

```text
http://127.0.0.1:7777
```

Para escolher host e porta:

```bash
uv run crucible serve --host 0.0.0.0 --port 7777
```

Passo a passo:

1. Rode `uv run crucible serve`.
2. Abra `http://127.0.0.1:7777`.
3. Clique em `Nova run`.
4. Escolha `Validate`, `Optimize` ou `Compare`.
5. Informe caminhos locais ou cole o conteúdo de `prompt`, `gabarito` e `config`.
6. Acompanhe a task até terminar.
7. Abra a run para ver score, verdicts, diffs, prompts e relatórios.

O dashboard é local e não tem autenticação. Use em rede confiável.

## O Que Mudou

O dashboard deixou de ser apenas uma listagem read-only. Ele agora também ajuda a
criar execuções locais, acompanhar tasks, interpretar resultados e decidir onde olhar
primeiro.

Use a UI quando quiser:

- rodar `validate` sem sair do navegador;
- iniciar `optimize` com arquivos locais ou conteúdo colado;
- comparar modelos alvo com o mesmo prompt e gabarito;
- acompanhar status/cancelamento de tasks;
- entender por que uma run parou;
- filtrar verdicts por falha, regressão, tag, assertion e score;
- gerar report HTML/JSON/PDF a partir da tela da run.

## Páginas Principais

### `/`

Lista runs com cards de resumo:

- total de runs;
- runs em andamento;
- runs concluídas;
- melhor score recente;
- custo total listado.

Filtros por query string:

- `status`
- `target`
- `min_score`

Exemplo:

```text
http://127.0.0.1:7777/?status=completed&target=ollama&min_score=80
```

### `/runs/{run_id}`

Mostra:

- modo da run (`Validate`, `Optimize` ou `Compare`);
- status;
- motivo de parada com descrição mais legível;
- melhor score;
- pass rate;
- threshold;
- custo total;
- p95 de latência;
- target/reasoning model;
- sugestão de próximo passo;
- contrato da tarefa e invariantes preservados;
- evolução por iteração;
- worst cases e tags mais fracas;
- tabela de iterações;
- melhor prompt.

Em runs de comparação, a tela também mostra um bloco `Comparação de modelos` com:

- vencedor por melhor score;
- vencedor por menor custo;
- vencedor por melhor custo-benefício;
- score, pass rate, custo, p95 e tokens cacheados por modelo;
- vencedor por caso.

Use essa tela para responder rapidamente:

- a run atingiu o objetivo?
- parou por plateau, budget ou limite de iterações?
- o score é alto, mas o pass rate segue baixo?
- quais casos devem ser investigados primeiro?

Quando uma proposta de refino é rejeitada por violar o contrato da tarefa, a tabela
de iterações mostra o motivo. Isso normalmente indica drift semântico, como trocar
extração literal por explicação ou remover uma regra de "não inventar".

Se houver tentativas de reparo, a mesma tabela mostra um badge com a quantidade de
reparos e um bloco expansível com as violações devolvidas ao `reasoning_model`. Use
isso para entender se o modelo corrigiu o prompt depois do feedback ou se a run
parou com `reasoning_failed_to_refine`.

### `/runs/new`

Cria uma task local.

O formulário aceita dois modos:

- `Validate`: mede o prompt atual e persiste o resultado como run de uma iteração.
- `Optimize`: executa o loop de otimização normal.
- `Compare`: executa uma iteração por item em `comparison_models`.

Para `prompt`, `gabarito` e `config`, a tela aceita caminho local ou conteúdo colado.
Se o conteúdo estiver preenchido, ele vence o caminho informado.

O campo `config` é um editor YAML completo. Ele cobre parâmetros como modelos,
budgets, threshold, `output_format`, split train/val/test, rate limits,
judge/embedding, cache de provider, comparação de modelos e multi-objective.

### `/tasks/{task_id}`

Mostra status da task:

- `queued`;
- `running`;
- `cancel_request`;
- `completed`;
- `failed`;
- `cancelled`.

Enquanto a task está ativa, a página atualiza automaticamente. Quando concluir, abre
link para a run gerada.

### `/runs/{run_id}/diff`

Mostra diff unificado de `v0` para `best` por padrão.

Query params opcionais:

- `from_version`
- `to_version`

### `/runs/{run_id}/iterations/{version}/verdicts`

Mostra verdicts de uma iteração com filtros:

- `case_id`
- `passed`
- `regression`
- `tag`
- `assertion_type`
- `min_score`
- `max_score`

Cada verdict pode ser expandido para ver input, expected output, actual output e
`assertion_detail`.

### `/runs/{run_id}/regressions`

Mostra verdicts marcados como regressão.

### `/compare`

Compara duas runs:

```text
/compare?left=<run-a>&right=<run-b>
```

## Endpoints JSON Do Dashboard

São endpoints read-only úteis para scripts locais:

- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/verdicts`
- `GET /api/runs/{run_id}/verdicts?version=1`

## Escopo

O dashboard não é multi-tenant e não tem autenticação. Ele é destinado a inspeção
local ou uso interno em rede confiável.

Quando você informa caminhos locais no formulário, o processo do dashboard lê esses
arquivos no filesystem da máquina onde `crucible serve` está rodando. Não exponha o
dashboard em rede pública.
