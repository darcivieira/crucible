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

Teste se a API está respondendo:

```bash
curl -s http://127.0.0.1:7788/runs
```

## Criar Run

```http
POST /runs
Content-Type: application/json
```

Exemplo com `curl` para uma validação simples:

```bash
curl -s -X POST http://127.0.0.1:7788/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "validate",
    "prompt": {
      "template": "Responda apenas: {input}",
      "variables": ["input"]
    },
    "gabarito": {
      "name": "sample",
      "version": "v1",
      "cases": [
        {
          "id": "case-001",
          "input": "ok",
          "expected_output": "ok",
          "assertion": {"type": "contains"}
        }
      ]
    },
    "config": {
      "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
      "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"}
    }
  }'
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

Com `curl`:

```bash
curl -s http://127.0.0.1:7788/tasks/<task-id>
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

Com `curl`:

```bash
curl -s -X POST http://127.0.0.1:7788/tasks/<task-id>/cancel
```

Marca `cancel_requested=true`. O optimizer observa esse estado entre iterações e
antes de executar novos casos. Chamadas de provider já em andamento não são
interrompidas à força.

## Listar Runs

```http
GET /runs
```

Retorna summaries das runs.

Com `curl`:

```bash
curl -s http://127.0.0.1:7788/runs
```

## Obter Run

```http
GET /runs/{run_id}
```

Retorna o `OptimizationRun` serializado completo.

Com `curl`:

```bash
curl -s http://127.0.0.1:7788/runs/<run-id>
```

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

Com `curl`:

```bash
curl -s -X POST http://127.0.0.1:7788/runs/<run-id>/reports/html
```

## Criar Comparação De Modelos

Em `mode: compare`, `target_model` e `reasoning_model` podem ficar ausentes. Informe
os candidatos em `comparison_models`:

```bash
curl -s -X POST http://127.0.0.1:7788/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "compare",
    "prompt": {
      "template": "Responda apenas: {input}",
      "variables": ["input"]
    },
    "gabarito": {
      "name": "compare-sample",
      "version": "v1",
      "cases": [
        {
          "id": "case-001",
          "input": "ok",
          "expected_output": "ok",
          "assertion": {"type": "contains"}
        }
      ]
    },
    "config": {
      "comparison_models": [
        {
          "label": "fake-a",
          "model": {"provider": "fake", "model_id": "target-a", "role": "target"}
        },
        {
          "label": "fake-b",
          "model": {"provider": "fake", "model_id": "target-b", "role": "target"}
        }
      ]
    }
  }'
```

## Notas Operacionais

- Não há autenticação ainda.
- Execução em background usa `FastAPI BackgroundTasks`.
- Para uso multiusuário ou produção, adicione autenticação antes de expor a API.
