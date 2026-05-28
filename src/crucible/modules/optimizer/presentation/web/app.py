# ruff: noqa: E501

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs
from uuid import uuid4

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import DictLoader, Environment, select_autoescape
from pydantic import ValidationError

from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore, TaskRecord
from crucible.modules.optimizer.application.reports import write_report
from crucible.modules.optimizer.application.tasks import (
    RunTaskRequest,
    next_step_hint,
    run_mode_label,
    run_task,
    stop_reason_label,
)
from crucible.modules.optimizer.domain.models import (
    Gabarito,
    Iteration,
    OptimizationConfig,
    OptimizationRun,
    Prompt,
    RunMode,
)


def create_dashboard_app(store: SQLiteRunStore | None = None) -> FastAPI:
    settings = get_settings()
    run_store = store or SQLiteRunStore(settings.sqlite_path)
    templates = _templates()
    app = FastAPI(title="Crucible Dashboard", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        status: str | None = None,
        target: str | None = None,
        min_score: float | None = None,
    ) -> str:
        all_runs = run_store.list_runs(limit=100)
        runs = all_runs
        if status:
            runs = [run for run in runs if run.status == status]
        if target:
            runs = [
                run
                for run in runs
                if target.lower() in run.target_model.lower()
                or target.lower() in run.reasoning_model.lower()
            ]
        if min_score is not None:
            runs = [
                run for run in runs if run.best_score is not None and run.best_score >= min_score
            ]
        return templates.get_template("index.html").render(
            request=request,
            runs=runs,
            summary=_index_summary(all_runs),
            filters={"status": status or "", "target": target or "", "min_score": min_score},
        )

    @app.get("/runs/new", response_class=HTMLResponse)
    async def new_run(request: Request) -> str:
        return templates.get_template("new_run.html").render(
            request=request,
            values=_default_form_values(),
            errors=[],
        )

    @app.post("/runs/new", response_class=HTMLResponse)
    async def create_run_from_form(
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        values = await _form_values(request)
        try:
            run_request = _run_request_from_form(values)
        except ValueError as exc:
            return HTMLResponse(
                templates.get_template("new_run.html").render(
                    request=request,
                    values={**_default_form_values(), **values},
                    errors=[str(exc)],
                ),
                status_code=422,
            )
        task_id = uuid4().hex
        run_store.create_task(task_id, "queued")
        background_tasks.add_task(run_task, task_id, run_request, run_store)
        return RedirectResponse(f"/tasks/{task_id}", status_code=303)

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    async def task_detail(request: Request, task_id: str) -> str:
        task = _get_task_or_404(run_store, task_id)
        return templates.get_template("task.html").render(request=request, task=task)

    @app.post("/tasks/{task_id}/cancel", response_class=HTMLResponse)
    async def cancel_task(task_id: str) -> RedirectResponse:
        _get_task_or_404(run_store, task_id)
        run_store.request_task_cancel(task_id)
        return RedirectResponse(f"/tasks/{task_id}", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str) -> str:
        run = await _load_run_or_404(run_store, run_id)
        best = run.best_iteration
        return templates.get_template("run.html").render(
            request=request,
            run=run,
            best=best,
            score_history=[iteration.score for iteration in run.iterations],
            hint=next_step_hint(
                run.stop_reason,
                best.score if best else None,
                best.score_report.pass_rate if best else None,
            ),
            stop_label=stop_reason_label(run.stop_reason),
            mode_label=run_mode_label(run.run_mode),
            weak_tags=_weak_tags(best.score_report.by_tag if best else {}),
        )

    @app.get("/runs/{run_id}/iterations/{version}/verdicts", response_class=HTMLResponse)
    async def iteration_verdicts(
        request: Request,
        run_id: str,
        version: int,
        case_id: str | None = None,
        passed: str | None = None,
        regression: str | None = None,
        tag: str | None = None,
        assertion_type: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
    ) -> str:
        run = await _load_run_or_404(run_store, run_id)
        iteration = _iteration_or_404(run, version)
        verdicts = _filter_verdicts(
            run_store.verdict_payloads(run.id, iteration_version=version),
            case_id=case_id,
            passed=passed,
            regression=regression,
            tag=tag,
            assertion_type=assertion_type,
            min_score=min_score,
            max_score=max_score,
        )
        return templates.get_template("verdicts.html").render(
            request=request,
            run=run,
            version=version,
            iteration=iteration,
            verdicts=verdicts,
            filters={
                "case_id": case_id or "",
                "passed": passed or "",
                "regression": regression or "",
                "tag": tag or "",
                "assertion_type": assertion_type or "",
                "min_score": min_score,
                "max_score": max_score,
            },
        )

    @app.get("/runs/{run_id}/regressions", response_class=HTMLResponse)
    async def regressions(request: Request, run_id: str) -> str:
        run = await _load_run_or_404(run_store, run_id)
        verdicts = [
            verdict
            for verdict in run_store.verdict_payloads(run.id)
            if verdict.get("is_regression")
        ]
        return templates.get_template("verdicts.html").render(
            request=request,
            run=run,
            version="regressions",
            verdicts=verdicts,
            filters={},
        )

    @app.get("/runs/{run_id}/diff", response_class=HTMLResponse)
    async def run_diff(
        request: Request,
        run_id: str,
        from_version: int = 0,
        to_version: str = "best",
    ) -> str:
        run = await _load_run_or_404(run_store, run_id)
        if not run.iterations:
            raise HTTPException(status_code=404, detail="Run has no iterations")
        try:
            left = run.iterations[from_version]
            right = run.best_iteration if to_version == "best" else run.iterations[int(to_version)]
        except (IndexError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid diff version") from exc
        if right is None:
            raise HTTPException(status_code=404, detail="Run has no best iteration")
        diff = "\n".join(
            difflib.unified_diff(
                left.prompt.template.splitlines(),
                right.prompt.template.splitlines(),
                fromfile=f"v{left.version}",
                tofile=f"v{right.version}",
                lineterm="",
            )
        )
        return templates.get_template("diff.html").render(
            request=request,
            run=run,
            left=left,
            right=right,
            diff=diff,
        )

    @app.get("/runs/{run_id}/reports/{format}", response_class=HTMLResponse)
    async def create_report_page(request: Request, run_id: str, format: str) -> str:
        run = await _load_run_or_404(run_store, run_id)
        if format not in {"json", "html", "pdf"}:
            raise HTTPException(status_code=422, detail="Supported formats: json, html, pdf")
        path = write_report(run, settings.reports_dir, format)
        return templates.get_template("report_created.html").render(
            request=request,
            run=run,
            format=format,
            path=path,
        )

    @app.get("/compare", response_class=HTMLResponse)
    async def compare(request: Request, left: str, right: str) -> str:
        try:
            left_run = await run_store.load_run(left)
            right_run = await run_store.load_run(right)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.get_template("compare.html").render(
            request=request,
            left=left_run,
            right=right_run,
            left_best=left_run.best_iteration,
            right_best=right_run.best_iteration,
        )

    @app.get("/api/runs")
    async def api_runs() -> list[dict[str, Any]]:
        return [summary.model_dump(mode="json") for summary in run_store.list_runs(limit=100)]

    @app.get("/api/runs/{run_id}")
    async def api_run(run_id: str) -> dict[str, Any]:
        run = await _load_run_or_404(run_store, run_id)
        return run.model_dump(mode="json")

    @app.get("/api/runs/{run_id}/verdicts")
    async def api_verdicts(run_id: str, version: int | None = None) -> list[dict[str, Any]]:
        return run_store.verdict_payloads(run_id, iteration_version=version)

    return app


async def _load_run_or_404(store: SQLiteRunStore, run_id: str):
    try:
        return await store.load_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _iteration_or_404(run: OptimizationRun, version: int) -> Iteration:
    for iteration in run.iterations:
        if iteration.version == version:
            return iteration
    raise HTTPException(status_code=404, detail=f"Iteration {version} not found")


def _get_task_or_404(store: SQLiteRunStore, task_id: str) -> TaskRecord:
    try:
        return store.get_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


async def _form_values(request: Request) -> dict[str, str]:
    body = (await request.body()).decode()
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1].strip() for key, values in parsed.items()}


def _run_request_from_form(values: Mapping[str, str]) -> RunTaskRequest:
    mode = values.get("mode", "optimize")
    if mode not in {"validate", "optimize", "compare"}:
        raise ValueError("Modo deve ser validate, optimize ou compare.")
    try:
        prompt = Prompt(template=_read_value(values, "prompt"), variables=["input"])
        gabarito = Gabarito.model_validate(yaml.safe_load(_read_value(values, "gabarito")))
        config = OptimizationConfig.model_validate(yaml.safe_load(_read_value(values, "config")))
    except (OSError, ValidationError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"Não foi possível montar a run: {exc}") from exc
    return RunTaskRequest(prompt=prompt, gabarito=gabarito, config=config, mode=cast(RunMode, mode))


def _read_value(values: Mapping[str, str], name: str) -> str:
    content = values.get(f"{name}_content", "").strip()
    if content:
        return content
    path_value = values.get(f"{name}_path", "").strip()
    if path_value:
        return Path(path_value).read_text(encoding="utf-8")
    raise ValueError(f"Informe o conteúdo ou caminho de {name}.")


def _default_form_values() -> dict[str, str]:
    return {
        "mode": "optimize",
        "prompt_path": "prompt.txt",
        "gabarito_path": "gabarito.yaml",
        "config_path": "config.yaml",
        "prompt_content": "Classifique o texto abaixo.\n\nEntrada:\n{input}",
        "gabarito_content": """name: dashboard-sample
version: v1
cases:
  - id: sample-001
    input: "cliente prometeu pagar em 7 dias"
    expected_output: "pagamento"
    assertion:
      type: contains
    tags: [sample]
""",
        "config_content": """threshold: 95.0
max_iterations: 3
max_cost_usd: 1.0
max_wallclock_seconds: 1800
parallelism: 2
target_model:
  provider: fake
  model_id: target
  role: target
reasoning_model:
  provider: fake
  model_id: reasoning
  role: reasoning
""",
    }


def _index_summary(runs: list[Any]) -> dict[str, Any]:
    completed = [run for run in runs if run.status == "completed"]
    best_scores = [run.best_score for run in runs if run.best_score is not None]
    return {
        "total": len(runs),
        "running": len([run for run in runs if run.status in {"queued", "running"}]),
        "completed": len(completed),
        "best_score": max(best_scores) if best_scores else None,
        "total_cost": sum(run.total_cost_usd for run in runs),
    }


def _weak_tags(scores: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: item[1])[:5]


def _filter_verdicts(
    verdicts: list[dict[str, Any]],
    *,
    case_id: str | None,
    passed: str | None,
    regression: str | None,
    tag: str | None,
    assertion_type: str | None,
    min_score: float | None,
    max_score: float | None,
) -> list[dict[str, Any]]:
    filtered = verdicts
    if case_id:
        filtered = [
            verdict
            for verdict in filtered
            if case_id.lower() in verdict["test_case"]["id"].lower()
        ]
    if passed in {"true", "false"}:
        wanted = passed == "true"
        filtered = [verdict for verdict in filtered if bool(verdict.get("passed")) is wanted]
    if regression in {"true", "false"}:
        wanted = regression == "true"
        filtered = [verdict for verdict in filtered if bool(verdict.get("is_regression")) is wanted]
    if tag:
        filtered = [
            verdict
            for verdict in filtered
            if tag in verdict.get("test_case", {}).get("tags", [])
        ]
    if assertion_type:
        filtered = [
            verdict
            for verdict in filtered
            if verdict.get("test_case", {}).get("assertion", {}).get("type") == assertion_type
        ]
    if min_score is not None:
        filtered = [verdict for verdict in filtered if float(verdict.get("score", 0.0)) >= min_score]
    if max_score is not None:
        filtered = [verdict for verdict in filtered if float(verdict.get("score", 0.0)) <= max_score]
    return filtered


def _templates() -> Environment:
    env = Environment(
        loader=DictLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["score"] = _score
    env.filters["money"] = _money
    env.filters["percent"] = _percent
    env.filters["stop_label"] = stop_reason_label
    env.filters["mode_label"] = run_mode_label
    env.filters["pretty_json"] = _pretty_json
    env.globals["model_label"] = _model_label
    return env


def _score(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _money(value: float | None) -> str:
    return "$0.0000" if value is None else f"${value:.4f}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def _model_label(model: Any | None) -> str:
    if model is None:
        return "-"
    return f"{model.provider}/{model.model_id}"


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


_BASE_STYLE = """
:root {
  color-scheme: light;
  --bg: #f5f7fa;
  --surface: #ffffff;
  --surface-soft: #f8fafc;
  --border: #d9e2ec;
  --text: #172026;
  --muted: #5f6f7f;
  --brand: #0f609b;
  --brand-strong: #074d7d;
  --ok: #1f7a4d;
  --warn: #a15c00;
  --bad: #b42318;
}
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0;
  color: var(--text);
  background: var(--bg);
}
header {
  background: #12202f;
  color: white;
  padding: 14px 28px;
}
header nav {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
header a { color: white; margin-left: 16px; }
main { padding: 24px 28px; max-width: 1280px; margin: 0 auto; }
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3 { margin: 0 0 12px; line-height: 1.2; }
p { line-height: 1.5; }
.muted { color: var(--muted); }
.page-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.button, button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--brand);
  background: var(--brand);
  color: white;
  padding: 8px 12px;
  border-radius: 6px;
  font: inherit;
  cursor: pointer;
}
.button.secondary, button.secondary {
  background: white;
  color: var(--brand);
}
.button.danger, button.danger {
  border-color: var(--bad);
  background: var(--bad);
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin: 18px 0;
}
.metric {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 14px;
  border-radius: 8px;
}
.metric span { display: block; font-size: 12px; color: var(--muted); }
.metric strong { display: block; font-size: 24px; margin-top: 4px; }
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
}
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th { background: #eef2f7; font-size: 12px; text-transform: uppercase; color: var(--muted); }
tr:hover td { background: #fbfdff; }
.badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  background: #e6f0f8;
  color: var(--brand-strong);
}
.badge.ok { background: #e7f6ee; color: var(--ok); }
.badge.warn { background: #fff4df; color: var(--warn); }
.badge.bad { background: #fdecea; color: var(--bad); }
label { display: block; font-weight: 650; margin-bottom: 6px; }
input, select, textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font: inherit;
  background: white;
  color: var(--text);
}
textarea {
  min-height: 210px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}
.help { color: var(--muted); font-size: 13px; margin-top: 4px; }
.error {
  border: 1px solid #f4b4ad;
  background: #fff4f2;
  color: var(--bad);
  padding: 12px;
  border-radius: 8px;
  margin: 12px 0;
}
pre {
  white-space: pre-wrap;
  background: #132638;
  color: #f0f4f8;
  padding: 14px;
  overflow: auto;
  border-radius: 8px;
}
details {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--surface-soft);
}
summary { cursor: pointer; font-weight: 650; }
.bar { display: flex; align-items: center; gap: 8px; min-width: 160px; }
.bar span {
  display: inline-block;
  background: var(--brand);
  height: 10px;
  min-width: 2px;
  border-radius: 999px;
}
.filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  align-items: end;
}
@media (max-width: 820px) {
  main { padding: 18px 14px; }
  .page-head, header nav { flex-direction: column; align-items: stretch; }
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
  table { display: block; overflow-x: auto; }
}
"""


_TEMPLATES: Mapping[str, str] = {
    "base.html": """
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title or "Crucible Dashboard" }}</title>
  <style>"""
    + _BASE_STYLE
    + """</style>
</head>
<body>
  <header>
    <nav>
      <div><strong>Crucible</strong> <span class="muted">dashboard local</span></div>
      <div>
        <a href="/">Runs</a>
        <a href="/runs/new">Nova run</a>
        <a href="/docs" target="_blank">API docs</a>
      </div>
    </nav>
  </header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
""",
    "index.html": """
{% extends "base.html" %}
{% block content %}
<div class="page-head">
  <div>
    <h1>Runs</h1>
    <p class="muted">Histórico local para investigar qualidade, custo e regressões.</p>
  </div>
  <div class="actions"><a class="button" href="/runs/new">Nova run</a></div>
</div>
<div class="metrics">
  <div class="metric"><span>Total</span><strong>{{ summary.total }}</strong></div>
  <div class="metric"><span>Em andamento</span><strong>{{ summary.running }}</strong></div>
  <div class="metric"><span>Concluídas</span><strong>{{ summary.completed }}</strong></div>
  <div class="metric"><span>Melhor score</span><strong>{{ summary.best_score|score }}</strong></div>
  <div class="metric"><span>Custo total</span><strong>{{ summary.total_cost|money }}</strong></div>
</div>
<form method="get" class="panel filters">
  <div><label>Status</label><input name="status" value="{{ filters.status }}"></div>
  <div><label>Modelo</label><input name="target" value="{{ filters.target }}"></div>
  <div><label>Score mínimo</label><input name="min_score" type="number" step="0.1" value="{{ filters.min_score or '' }}"></div>
  <div><button type="submit">Filtrar</button></div>
</form>
<table>
  <thead>
    <tr><th>Run</th><th>Modo</th><th>Status</th><th>Melhor</th><th>Custo</th><th>Target</th><th>Parada</th><th>Início</th></tr>
  </thead>
  <tbody>
  {% for run in runs %}
    <tr>
      <td><a href="/runs/{{ run.id }}">{{ run.id[:12] }}</a><br><span class="muted">{{ run.id }}</span></td>
      <td><span class="badge">{{ run.run_mode|mode_label }}</span></td>
      <td><span class="badge {% if run.status == 'completed' %}ok{% elif run.status in ['failed', 'aborted'] %}bad{% else %}warn{% endif %}">{{ run.status }}</span></td>
      <td>{{ run.best_score|score }}</td>
      <td>{{ run.total_cost_usd|money }}</td>
      <td>{{ run.target_model }}</td>
      <td>{{ run.stop_reason|stop_label }}</td>
      <td>{{ run.started_at }}</td>
    </tr>
  {% else %}
    <tr><td colspan="8">Nenhuma run encontrada.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
""",
    "new_run.html": """
{% extends "base.html" %}
{% block content %}
<div class="page-head">
  <div>
    <h1>Nova run</h1>
    <p class="muted">Crie validações rápidas ou otimizações completas a partir de arquivos locais ou conteúdo editado.</p>
  </div>
  <div class="actions"><a class="button secondary" href="/">Voltar</a></div>
</div>
{% for error in errors %}<div class="error">{{ error }}</div>{% endfor %}
<form method="post">
  <section class="panel">
    <div class="grid-3">
      <div>
        <label>Modo</label>
        <select name="mode">
          <option value="optimize" {% if values.mode == 'optimize' %}selected{% endif %}>Optimize</option>
          <option value="validate" {% if values.mode == 'validate' %}selected{% endif %}>Validate</option>
          <option value="compare" {% if values.mode == 'compare' %}selected{% endif %}>Compare models</option>
        </select>
        <div class="help">Validate mede o prompt atual. Optimize tenta gerar versões melhores. Compare executa uma versão por modelo em comparison_models.</div>
      </div>
      <div>
        <label>Prompt path</label>
        <input name="prompt_path" value="{{ values.prompt_path }}">
      </div>
      <div>
        <label>Gabarito path</label>
        <input name="gabarito_path" value="{{ values.gabarito_path }}">
      </div>
    </div>
  </section>
  <section class="grid-2">
    <div class="panel">
      <label>Prompt</label>
      <textarea name="prompt_content">{{ values.prompt_content }}</textarea>
      <div class="help">Se preenchido, este conteúdo vence o caminho informado.</div>
    </div>
    <div class="panel">
      <label>Gabarito YAML/JSON</label>
      <textarea name="gabarito_content">{{ values.gabarito_content }}</textarea>
      <div class="help">Casos, expected_output, assertion, weights e tags vivem aqui.</div>
    </div>
  </section>
  <section class="panel">
    <div class="grid-2">
      <div>
        <label>Config path</label>
        <input name="config_path" value="{{ values.config_path }}">
      </div>
      <div>
        <label>Config YAML</label>
        <div class="help">Este editor cobre todos os parâmetros da run: modelos, budgets, output_format, split, judge, rate limit e multi-objective.</div>
      </div>
    </div>
    <textarea name="config_content">{{ values.config_content }}</textarea>
  </section>
  <section class="panel">
    <h2>Leitura dos parâmetros</h2>
    <div class="grid-3">
      <p><strong>threshold</strong><br><span class="muted">Score global de parada, em escala 0-100.</span></p>
      <p><strong>max_iterations</strong><br><span class="muted">Quantidade máxima de versões, incluindo v0.</span></p>
      <p><strong>output_format</strong><br><span class="muted">Contrato pedido ao provider; a assertion mede se foi cumprido.</span></p>
      <p><strong>use_gabarito_split</strong><br><span class="muted">Separa train/val/test para reduzir overfitting.</span></p>
      <p><strong>rate_limit</strong><br><span class="muted">Controla concorrência e retry por modelo.</span></p>
      <p><strong>field_by_field.weights</strong><br><span class="muted">Fica no gabarito, não no config.</span></p>
    </div>
  </section>
  <div class="actions">
    <button type="submit">Iniciar run</button>
    <a class="button secondary" href="/">Cancelar</a>
  </div>
</form>
{% endblock %}
""",
    "task.html": """
{% extends "base.html" %}
{% block content %}
<div class="page-head">
  <div>
    <h1>Task {{ task.id[:12] }}</h1>
    <p class="muted">Status atualizado após cada execução em background.</p>
  </div>
  <div class="actions"><a class="button secondary" href="/">Runs</a></div>
</div>
<div class="metrics">
  <div class="metric"><span>Status</span><strong>{{ task.status }}</strong></div>
  <div class="metric"><span>Run</span><strong>{% if task.run_id %}<a href="/runs/{{ task.run_id }}">abrir</a>{% else %}-{% endif %}</strong></div>
  <div class="metric"><span>Cancelamento</span><strong>{{ "sim" if task.cancel_requested else "não" }}</strong></div>
  <div class="metric"><span>Atualizada</span><strong>{{ task.updated_at }}</strong></div>
</div>
{% if task.error %}<div class="error">{{ task.error }}</div>{% endif %}
{% if task.status not in ["completed", "failed", "cancelled"] %}
<form method="post" action="/tasks/{{ task.id }}/cancel"><button class="danger" type="submit">Cancelar task</button></form>
{% endif %}
{% if task.status in ["queued", "running", "cancel_requested"] %}
<script>setTimeout(function(){ window.location.reload(); }, 2500);</script>
{% endif %}
{% endblock %}
""",
    "run.html": """
{% extends "base.html" %}
{% block content %}
<div class="page-head">
  <div>
    <p><a href="/">Runs</a></p>
    <h1>Run {{ run.id[:12] }}</h1>
    <p class="muted">{{ mode_label }} · {{ stop_label }} · {{ run.id }}</p>
  </div>
  <div class="actions">
    <a class="button secondary" href="/runs/{{ run.id }}/diff">Diff v0 → best</a>
    <a class="button secondary" href="/runs/{{ run.id }}/regressions">Regressões</a>
    <a class="button secondary" href="/runs/{{ run.id }}/reports/html">Report HTML</a>
    <a class="button secondary" href="/api/runs/{{ run.id }}">JSON</a>
  </div>
</div>
<div class="metrics">
  <div class="metric"><span>Status</span><strong>{{ run.status }}</strong></div>
  <div class="metric"><span>Best score</span><strong>{{ best.score|score if best else "-" }}</strong></div>
  <div class="metric"><span>Pass rate</span><strong>{{ best.score_report.pass_rate|percent if best else "-" }}</strong></div>
  <div class="metric"><span>Threshold</span><strong>{{ run.config.threshold|score }}</strong></div>
  <div class="metric"><span>Custo</span><strong>{{ run.total_cost_usd|money }}</strong></div>
  <div class="metric"><span>p95 latency</span><strong>{{ "%.0f ms"|format(best.score_report.operational.p95_latency_ms) if best else "-" }}</strong></div>
</div>
<div class="panel">
  <h2>Próximo passo sugerido</h2>
  <p>{{ hint }}</p>
  <p class="muted">Target: {{ model_label(run.config.target_model) }} · Reasoning: {{ model_label(run.config.reasoning_model) }}</p>
</div>
{% if run.comparison_summary %}
<div class="metrics">
  <div class="metric"><span>Melhor score</span><strong>{{ run.comparison_summary.best_score.label }}</strong></div>
  <div class="metric"><span>Menor custo</span><strong>{{ run.comparison_summary.lowest_cost.label }}</strong></div>
  <div class="metric"><span>Melhor custo-benefício</span><strong>{{ run.comparison_summary.best_value.label }}</strong></div>
</div>
<section class="panel">
  <h2>Comparação de modelos</h2>
  <table>
    <thead><tr><th>Modelo</th><th>Score</th><th>Pass rate</th><th>Custo</th><th>p95</th><th>Cached tokens</th></tr></thead>
    <tbody>
    {% for iteration in run.iterations %}
      <tr>
        <td>{{ iteration.comparison_label or ("v" ~ iteration.version) }}</td>
        <td>{{ iteration.score|score }}</td>
        <td>{{ iteration.score_report.pass_rate|percent }}</td>
        <td>{{ iteration.score_report.operational.total_cost_usd|money }}</td>
        <td>{{ "%.0f ms"|format(iteration.score_report.operational.p95_latency_ms) }}</td>
        <td>{{ iteration.score_report.operational.cached_tokens }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  <details>
    <summary>Vencedores por case</summary>
    <table>
      <thead><tr><th>Case</th><th>Score</th><th>Custo</th><th>Custo-benefício</th></tr></thead>
      <tbody>
      {% for winner in run.comparison_summary.case_winners %}
        <tr><td>{{ winner.test_case_id }}</td><td>{{ winner.best_score }}</td><td>{{ winner.lowest_cost }}</td><td>{{ winner.best_value }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </details>
</section>
{% endif %}
{% if run.task_contract %}
<div class="panel">
  <h2>Contrato da tarefa</h2>
  <p class="muted">{{ run.task_contract.objective }}</p>
  {% if run.task_contract.literal_extraction_fields %}
    <p><strong>Extração literal:</strong> {{ run.task_contract.literal_extraction_fields|join(", ") }}</p>
  {% endif %}
  <details>
    <summary>Ver invariantes</summary>
    <ul>
      {% for rule in run.task_contract.invariants %}
        <li>{{ rule.text }} <span class="muted">({{ rule.source }})</span></li>
      {% endfor %}
      {% for rule in run.task_contract.negative_rules %}
        <li>{{ rule.text }} <span class="muted">({{ rule.source }})</span></li>
      {% endfor %}
    </ul>
  </details>
</div>
{% endif %}
<div class="grid-2">
  <section class="panel">
    <h2>Evolução</h2>
    {% for iteration in run.iterations %}
      <div class="bar">
        <a href="/runs/{{ run.id }}/iterations/{{ iteration.version }}/verdicts">v{{ iteration.version }}</a>
        <span style="width: {{ iteration.score }}%;"></span>
        <strong>{{ iteration.score|score }}</strong>
      </div>
    {% endfor %}
  </section>
  <section class="panel">
    <h2>Onde olhar primeiro</h2>
    {% if best and best.score_report.worst_case_ids %}
      <p><strong>Worst cases:</strong> {{ best.score_report.worst_case_ids|join(", ") }}</p>
    {% else %}
      <p class="muted">Sem worst cases registrados.</p>
    {% endif %}
    {% if weak_tags %}
      <p><strong>Tags mais fracas:</strong></p>
      <ul>{% for tag, score in weak_tags %}<li>{{ tag }}: {{ score|score }}</li>{% endfor %}</ul>
    {% endif %}
  </section>
</div>
<h2>Iterações</h2>
<table>
  <thead>
    <tr><th>Versão</th><th>Score</th><th>Pass rate</th><th>Custo</th><th>p95</th><th>Mudança</th><th>Ações</th></tr>
  </thead>
  <tbody>
  {% for iteration in run.iterations %}
    <tr>
      <td>v{{ iteration.version }}</td>
      <td>{{ iteration.score|score }}</td>
      <td>{{ iteration.score_report.pass_rate|percent }}</td>
      <td>{{ iteration.score_report.operational.total_cost_usd|money }}</td>
      <td>{{ "%.0f ms"|format(iteration.score_report.operational.p95_latency_ms) }}</td>
      <td>
        {{ iteration.diff_summary or "-" }}
        {% if iteration.refinement_repair_attempts %}
          <br><span class="badge warn">{{ iteration.refinement_repair_attempts|length }} reparo(s)</span>
          <details>
            <summary>Tentativas do reasoning</summary>
            <ol>
              {% for attempt in iteration.refinement_repair_attempts %}
                <li>
                  <strong>#{{ attempt.attempt }}</strong>:
                  {{ attempt.violations|join("; ") }}
                  {% if attempt.diff_summary %}
                    <br><span class="muted">{{ attempt.diff_summary }}</span>
                  {% endif %}
                </li>
              {% endfor %}
            </ol>
          </details>
        {% endif %}
        {% if iteration.refinement_rejected_reason %}
          <br><span class="badge bad">refino rejeitado</span>
          <br><span class="muted">{{ iteration.refinement_rejected_reason }}</span>
        {% endif %}
      </td>
      <td>
        <a href="/runs/{{ run.id }}/iterations/{{ iteration.version }}/verdicts">Verdicts</a>
        · <a href="/runs/{{ run.id }}/diff?from_version=0&to_version={{ iteration.version }}">Diff</a>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
<section class="panel">
  <h2>Best prompt</h2>
  <pre>{{ best.prompt.template if best else "" }}</pre>
</section>
{% endblock %}
""",
    "verdicts.html": """
{% extends "base.html" %}
{% block content %}
<div class="page-head">
  <div>
    <p><a href="/runs/{{ run.id }}">Run {{ run.id[:12] }}</a></p>
    <h1>Verdicts {{ version }}</h1>
    <p class="muted">Filtre falhas, regressões e assertions para achar o primeiro ponto de ação.</p>
  </div>
</div>
{% if iteration is defined %}
  <section class="panel">
    <h2>Prompt utilizado</h2>
    <p class="muted">
      Este é o prompt da v{{ iteration.version }} usado para executar todos os cases
      listados abaixo. O placeholder como <code>{input}</code> é preenchido com o
      input de cada case durante a execução.
    </p>
    <pre>{{ iteration.prompt.template }}</pre>
  </section>
{% endif %}
<form method="get" class="panel filters">
  <div><label>Case</label><input name="case_id" value="{{ filters.case_id }}"></div>
  <div><label>Passed</label><select name="passed"><option value=""></option><option value="true" {% if filters.passed == 'true' %}selected{% endif %}>true</option><option value="false" {% if filters.passed == 'false' %}selected{% endif %}>false</option></select></div>
  <div><label>Regression</label><select name="regression"><option value=""></option><option value="true" {% if filters.regression == 'true' %}selected{% endif %}>true</option><option value="false" {% if filters.regression == 'false' %}selected{% endif %}>false</option></select></div>
  <div><label>Tag</label><input name="tag" value="{{ filters.tag }}"></div>
  <div><label>Assertion</label><input name="assertion_type" value="{{ filters.assertion_type }}"></div>
  <div><label>Min score</label><input name="min_score" type="number" step="0.01" value="{{ filters.min_score or '' }}"></div>
  <div><label>Max score</label><input name="max_score" type="number" step="0.01" value="{{ filters.max_score or '' }}"></div>
  <div><button type="submit">Filtrar</button></div>
</form>
<table>
  <thead>
    <tr><th>Case</th><th>Score</th><th>Passed</th><th>Regression</th><th>Assertion</th><th>Latency</th><th>Tags</th></tr>
  </thead>
  <tbody>
  {% for verdict in verdicts %}
    <tr>
      <td>
        <details>
          <summary>{{ verdict.test_case.id }}</summary>
          <h3>Input</h3><pre>{{ verdict.test_case.input }}</pre>
          <h3>Expected</h3><pre>{{ verdict.test_case.expected_output }}</pre>
          <h3>Actual</h3><pre>{{ verdict.execution.actual_output }}</pre>
          <h3>Assertion detail</h3><pre>{{ verdict.assertion_detail|pretty_json }}</pre>
        </details>
      </td>
      <td>{{ verdict.score|score }}</td>
      <td><span class="badge {% if verdict.passed %}ok{% else %}bad{% endif %}">{{ verdict.passed }}</span></td>
      <td>{{ verdict.is_regression }}</td>
      <td>{{ verdict.test_case.assertion.type }}</td>
      <td>{{ "%.0f ms"|format(verdict.execution.latency_ms) }}</td>
      <td>{{ verdict.test_case.tags|join(", ") }}</td>
    </tr>
  {% else %}
    <tr><td colspan="7">Nenhum verdict encontrado.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
""",
    "diff.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/runs/{{ run.id }}">Run {{ run.id[:12] }}</a></p>
<h1>Diff v{{ left.version }} → v{{ right.version }}</h1>
<form method="get" class="panel filters">
  <div><label>From</label><input name="from_version" type="number" value="{{ left.version }}"></div>
  <div><label>To</label><input name="to_version" value="{{ right.version }}"></div>
  <div><button type="submit">Atualizar</button></div>
</form>
<pre>{{ diff }}</pre>
{% endblock %}
""",
    "report_created.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/runs/{{ run.id }}">Run {{ run.id[:12] }}</a></p>
<h1>Report {{ format }}</h1>
<div class="panel">
  <p>Report gerado em:</p>
  <pre>{{ path }}</pre>
</div>
{% endblock %}
""",
    "compare.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/">Runs</a></p>
<h1>Compare Runs</h1>
<table>
  <thead><tr><th>Métrica</th><th>{{ left.id[:12] }}</th><th>{{ right.id[:12] }}</th></tr></thead>
  <tbody>
    <tr><td>Best score</td><td>{{ left_best.score|score if left_best else "-" }}</td><td>{{ right_best.score|score if right_best else "-" }}</td></tr>
    <tr><td>Pass rate</td><td>{{ left_best.score_report.pass_rate|percent if left_best else "-" }}</td><td>{{ right_best.score_report.pass_rate|percent if right_best else "-" }}</td></tr>
    <tr><td>Iterações</td><td>{{ left.iterations|length }}</td><td>{{ right.iterations|length }}</td></tr>
    <tr><td>Custo</td><td>{{ left.total_cost_usd|money }}</td><td>{{ right.total_cost_usd|money }}</td></tr>
    <tr><td>Parada</td><td>{{ left.stop_reason|stop_label }}</td><td>{{ right.stop_reason|stop_label }}</td></tr>
  </tbody>
</table>
{% endblock %}
""",
}
