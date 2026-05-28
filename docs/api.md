# REST API

Suba a API:

```bash
uv run crucible api --port 7788
```

Base URL:

```text
http://127.0.0.1:7788
```

A API é intencionalmente fina. Ela usa o mesmo `Optimizer`, SQLite store e gerador
de relatórios que a CLI.

## Criar Run

```http
POST /runs
Content-Type: application/json
```

Body:

```json
{
  "mode": "optimize",
  "prompt": {
    "template": "Responda: {input}",
    "variables": ["input"],
    "metadata": {}
  },
  "gabarito": {
    "name": "sample",
    "version": "v1",
    "cases": [
      {
        "id": "case-001",
        "input": "Diga apenas ok",
        "expected_output": "ok",
        "assertion": {"type": "contains"},
        "weight": 1.0,
        "tags": ["smoke"]
      }
    ]
  },
  "config": {
    "threshold": 95.0,
    "max_iterations": 1,
    "max_cost_usd": 5.0,
    "target_model": {
      "provider": "fake",
      "model_id": "target",
      "role": "target"
    },
    "reasoning_model": {
      "provider": "fake",
      "model_id": "reasoning",
      "role": "reasoning"
    }
  }
}
```

`mode` é opcional. Valores aceitos:

- `optimize`: executa o loop de otimização e cria uma run normal.
- `validate`: executa apenas a versão atual do prompt e persiste uma run com uma
  iteração, `run_mode="validate"` e `stop_reason="validation_only"`.
- `compare`: executa uma iteração por item de `comparison_models`.

Para `validate`, `optimize` e `estimate-cost`, `config.target_model` e
`config.reasoning_model` são obrigatórios. Para `compare`, eles podem ficar ausentes;
nesse caso, informe apenas `comparison_models`.

Resposta:

```json
{
  "task_id": "abc123",
  "status": "queued"
}
```

## Consultar Status Da Task

```http
GET /tasks/{task_id}
```

Respostas possíveis:

```json
{"status": "queued"}
```

```json
{"status": "running"}
```

```json
{"status": "completed", "run_id": "...", "cancel_requested": false}
```

```json
{"status": "failed", "error": "..."}
```

O estado de task é persistido no SQLite em `api_tasks`, então reiniciar a API não
perde o histórico da task.

## Cancelar Task

```http
POST /tasks/{task_id}/cancel
```

Marca `cancel_requested=true`. O optimizer observa esse estado entre iterações e
antes de executar novos casos. Chamadas de provider já em andamento não são
interrompidas à força.

## Listar Runs

```http
GET /runs
```

Retorna summaries das runs.

## Obter Run

```http
GET /runs/{run_id}
```

Retorna o `OptimizationRun` serializado completo.

## Criar Relatório

```http
POST /runs/{run_id}/reports/{format}
```

Formatos:

- `json`
- `html`
- `pdf`

Resposta:

```json
{"path": ".crucible/reports/<run-id>.html"}
```

## Notas Operacionais

- Não há autenticação ainda.
- Execução em background usa `FastAPI BackgroundTasks`.
- Para uso multiusuário ou produção, adicione autenticação antes de expor a API.
