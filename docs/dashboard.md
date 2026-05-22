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

## Páginas

### `/`

Lista runs.

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

- status;
- motivo de parada;
- melhor score;
- custo total;
- target/reasoning model;
- gráfico de score;
- tabela de iterações;
- melhor prompt.

### `/runs/{run_id}/diff`

Mostra diff unificado de `v0` para `best` por padrão.

Query params opcionais:

- `from_version`
- `to_version`

### `/runs/{run_id}/iterations/{version}/verdicts`

Mostra verdicts de uma iteração.

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
