from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import DictLoader, Environment, select_autoescape

from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore


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
        runs = run_store.list_runs(limit=100)
        if status:
            runs = [run for run in runs if run.status == status]
        if target:
            runs = [run for run in runs if target.lower() in run.target_model.lower()]
        if min_score is not None:
            runs = [
                run for run in runs if run.best_score is not None and run.best_score >= min_score
            ]
        return templates.get_template("index.html").render(
            request=request,
            runs=runs,
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str) -> str:
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return templates.get_template("run.html").render(
            request=request,
            run=run,
            best=run.best_iteration,
            score_history=[iteration.score for iteration in run.iterations],
        )

    @app.get("/runs/{run_id}/iterations/{version}/verdicts", response_class=HTMLResponse)
    async def iteration_verdicts(request: Request, run_id: str, version: int) -> str:
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        verdicts = run_store.verdict_payloads(run.id, iteration_version=version)
        return templates.get_template("verdicts.html").render(
            request=request,
            run=run,
            version=version,
            verdicts=verdicts,
        )

    @app.get("/runs/{run_id}/regressions", response_class=HTMLResponse)
    async def regressions(request: Request, run_id: str) -> str:
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        )

    @app.get("/runs/{run_id}/diff", response_class=HTMLResponse)
    async def run_diff(
        request: Request,
        run_id: str,
        from_version: int = 0,
        to_version: str = "best",
    ) -> str:
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        left = run.iterations[from_version]
        right = run.best_iteration if to_version == "best" else run.iterations[int(to_version)]
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
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return run.model_dump(mode="json")

    @app.get("/api/runs/{run_id}/verdicts")
    async def api_verdicts(run_id: str, version: int | None = None) -> list[dict[str, Any]]:
        return run_store.verdict_payloads(run_id, iteration_version=version)

    return app


def _templates() -> Environment:
    env = Environment(
        loader=DictLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["score"] = _score
    env.filters["money"] = _money
    return env


def _score(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _money(value: float | None) -> str:
    return "$0.0000" if value is None else f"${value:.4f}"


_BASE_STYLE = """
body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; color: #172026; background: #f7f9fb; }
header { background: #111827; color: white; padding: 16px 28px; }
main { padding: 24px 28px; max-width: 1180px; margin: 0 auto; }
a { color: #0f609b; text-decoration: none; }
table { width: 100%; border-collapse: collapse; background: white; }
th, td { padding: 10px 12px; border-bottom: 1px solid #d9e2ec; text-align: left; }
th { background: #eef2f7; font-size: 13px; text-transform: uppercase; color: #52606d; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px;
           margin: 18px 0; }
.metric { background: white; border: 1px solid #d9e2ec; padding: 14px; }
.metric span { display: block; font-size: 12px; color: #627d98; }
.metric strong { font-size: 22px; }
.panel { background: white; border: 1px solid #d9e2ec; padding: 16px; margin: 18px 0; }
pre { white-space: pre-wrap; background: #102a43; color: #f0f4f8; padding: 16px; overflow: auto; }
.muted { color: #627d98; }
"""


_TEMPLATES: Mapping[str, str] = {
    "base.html": """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title or "Crucible Dashboard" }}</title>
  <style>"""
    + _BASE_STYLE
    + """</style>
</head>
<body>
  <header><strong>Crucible</strong> <span class="muted">local dashboard</span></header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
""",
    "index.html": """
{% extends "base.html" %}
{% block content %}
<h1>Runs</h1>
<form method="get" class="panel">
  <label>Status <input name="status"></label>
  <label>Target <input name="target"></label>
  <label>Min score <input name="min_score" type="number" step="0.1"></label>
  <button type="submit">Filter</button>
</form>
<table>
  <thead>
    <tr><th>Run</th><th>Status</th><th>Best</th><th>Cost</th><th>Target</th><th>Started</th></tr>
  </thead>
  <tbody>
  {% for run in runs %}
    <tr>
      <td><a href="/runs/{{ run.id }}">{{ run.id }}</a></td>
      <td>{{ run.status }}</td>
      <td>{{ run.best_score|score }}</td>
      <td>{{ run.total_cost_usd|money }}</td>
      <td>{{ run.target_model }}</td>
      <td>{{ run.started_at }}</td>
    </tr>
  {% else %}
    <tr><td colspan="6">No runs found.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
""",
    "run.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/">Runs</a></p>
<h1>Run {{ run.id }}</h1>
<div class="metrics">
  <div class="metric"><span>Status</span><strong>{{ run.status }}</strong></div>
  <div class="metric"><span>Stop reason</span><strong>{{ run.stop_reason }}</strong></div>
  <div class="metric">
    <span>Best score</span><strong>{{ best.score|score if best else "-" }}</strong>
  </div>
  <div class="metric"><span>Total cost</span><strong>{{ run.total_cost_usd|money }}</strong></div>
</div>
<div class="panel">
  <p>
    <strong>Target:</strong>
    {{ run.config.target_model.provider }}/{{ run.config.target_model.model_id }}
  </p>
  <p>
    <strong>Reasoning:</strong>
    {{ run.config.reasoning_model.provider }}/{{ run.config.reasoning_model.model_id }}
  </p>
  <p><a href="/runs/{{ run.id }}/diff">Diff v0 → best</a></p>
  <p><a href="/runs/{{ run.id }}/regressions">Regressions</a></p>
  <p><a href="/api/runs/{{ run.id }}">JSON payload</a></p>
</div>
<h2>Score chart</h2>
<div class="panel">
  {% for iteration in run.iterations %}
    <div style="margin: 6px 0;">
      v{{ iteration.version }}
      <span
        style="display:inline-block;background:#0f609b;height:10px;width:{{ iteration.score }}%;"
      ></span>
      {{ iteration.score|score }}
    </div>
  {% endfor %}
</div>
<h2>Iterations</h2>
<table>
  <thead>
    <tr>
      <th>Version</th><th>Score</th><th>Pass rate</th>
      <th>Cost</th><th>Worst cases</th>
    </tr>
  </thead>
  <tbody>
  {% for iteration in run.iterations %}
    <tr>
      <td>v{{ iteration.version }}</td>
      <td>{{ iteration.score|score }}</td>
      <td>{{ "%.0f%%"|format(iteration.score_report.pass_rate * 100) }}</td>
      <td>{{ iteration.score_report.operational.total_cost_usd|money }}</td>
      <td>{{ iteration.score_report.worst_case_ids|join(", ") }}</td>
      <td><a href="/runs/{{ run.id }}/iterations/{{ iteration.version }}/verdicts">Verdicts</a></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
<h2>Score history</h2>
<pre>{{ score_history }}</pre>
<h2>Best prompt</h2>
<pre>{{ best.prompt.template if best else "" }}</pre>
{% endblock %}
""",
    "verdicts.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/runs/{{ run.id }}">Run {{ run.id }}</a></p>
<h1>Verdicts {{ version }}</h1>
<table>
  <thead>
    <tr>
      <th>Case</th><th>Score</th><th>Passed</th><th>Regression</th>
      <th>Latency</th><th>Tags</th>
    </tr>
  </thead>
  <tbody>
  {% for verdict in verdicts %}
    <tr>
      <td>{{ verdict.test_case.id }}</td>
      <td>{{ verdict.score|score }}</td>
      <td>{{ verdict.passed }}</td>
      <td>{{ verdict.is_regression }}</td>
      <td>{{ verdict.execution.latency_ms }}</td>
      <td>{{ verdict.test_case.tags|join(", ") }}</td>
    </tr>
  {% else %}
    <tr><td colspan="6">No verdicts found.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
""",
    "diff.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/runs/{{ run.id }}">Run {{ run.id }}</a></p>
<h1>Diff v{{ left.version }} → v{{ right.version }}</h1>
<pre>{{ diff }}</pre>
{% endblock %}
""",
    "compare.html": """
{% extends "base.html" %}
{% block content %}
<p><a href="/">Runs</a></p>
<h1>Compare Runs</h1>
<table>
  <thead><tr><th>Metric</th><th>{{ left.id }}</th><th>{{ right.id }}</th></tr></thead>
  <tbody>
    <tr>
      <td>Best score</td>
      <td>{{ left_best.score|score if left_best else "-" }}</td>
      <td>{{ right_best.score|score if right_best else "-" }}</td>
    </tr>
    <tr>
      <td>Iterations</td>
      <td>{{ left.iterations|length }}</td>
      <td>{{ right.iterations|length }}</td>
    </tr>
    <tr>
      <td>Total cost</td>
      <td>{{ left.total_cost_usd|money }}</td>
      <td>{{ right.total_cost_usd|money }}</td>
    </tr>
    <tr><td>Stop reason</td><td>{{ left.stop_reason }}</td><td>{{ right.stop_reason }}</td></tr>
  </tbody>
</table>
{% endblock %}
""",
}
