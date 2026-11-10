# ruff: noqa: E501

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import parse_qs
from uuid import uuid4

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BeforeValidator, ValidationError

from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.compatibility import resolve_benchmark_path
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
    Benchmark,
    Iteration,
    OptimizationConfig,
    OptimizationRun,
    Prompt,
    RunMode,
)

_WEB_ROOT = Path(__file__).parent


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def create_dashboard_app(store: SQLiteRunStore | None = None) -> FastAPI:
    settings = get_settings()
    run_store = store or SQLiteRunStore(settings.sqlite_path)
    templates = _templates()
    app = FastAPI(title="Crucible Dashboard", version="0.1.0")
    app.mount("/static", StaticFiles(directory=_WEB_ROOT / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        status: str | None = None,
        target: str | None = None,
        min_score: Annotated[float | None, BeforeValidator(_blank_to_none)] = None,
        mode: str | None = None,
    ) -> str:
        all_runs = run_store.list_runs(limit=100)
        runs = all_runs
        if mode:
            runs = [run for run in runs if run.run_mode == mode]
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
            filters={
                "status": status or "",
                "target": target or "",
                "min_score": min_score,
                "mode": mode or "",
            },
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
            scorecard=_scorecard(run),
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
        min_score: Annotated[float | None, BeforeValidator(_blank_to_none)] = None,
        max_score: Annotated[float | None, BeforeValidator(_blank_to_none)] = None,
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
    async def regressions(
        request: Request,
        run_id: str,
        case_id: str | None = None,
        passed: str | None = None,
        regression: str | None = None,
        tag: str | None = None,
        assertion_type: str | None = None,
        min_score: Annotated[float | None, BeforeValidator(_blank_to_none)] = None,
        max_score: Annotated[float | None, BeforeValidator(_blank_to_none)] = None,
    ) -> str:
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
            verdicts=_filter_verdicts(
                verdicts,
                case_id=case_id,
                passed=passed,
                regression=regression,
                tag=tag,
                assertion_type=assertion_type,
                min_score=min_score,
                max_score=max_score,
            ),
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

    @app.get("/runs/{run_id}/reports/pdf/download")
    async def download_pdf_report(run_id: str) -> FileResponse:
        run = await _load_run_or_404(run_store, run_id)
        if run.status not in {"completed", "failed", "aborted"}:
            raise HTTPException(status_code=409, detail="Run has not finished yet")
        path = write_report(run, settings.reports_dir, "pdf")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=f"crucible-{run.id}.pdf",
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
            choices=run_store.list_runs(limit=100),
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
    values = dict(values)
    for suffix in ("content", "path"):
        key = f"benchmark_{suffix}"
        if not values.get(key):
            values[key] = values.get(f"gabarito_{suffix}", "")
    mode = values.get("mode", "optimize")
    if mode not in {"validate", "optimize", "compare"}:
        raise ValueError("Mode must be validate, optimize, or compare.")
    try:
        prompt = Prompt(template=_read_value(values, "prompt"), variables=["input"])
        benchmark = Benchmark.model_validate(yaml.safe_load(_read_value(values, "benchmark")))
        config = OptimizationConfig.model_validate(yaml.safe_load(_read_value(values, "config")))
    except (OSError, ValidationError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"Could not create the run: {exc}") from exc
    return RunTaskRequest(
        prompt=prompt, benchmark=benchmark, config=config, mode=cast(RunMode, mode)
    )


def _read_value(values: Mapping[str, str], name: str) -> str:
    content = values.get(f"{name}_content", "").strip()
    if content:
        return content
    path_value = values.get(f"{name}_path", "").strip()
    if path_value:
        path = Path(path_value)
        if name == "benchmark":
            path = resolve_benchmark_path(path)
        return path.read_text(encoding="utf-8")
    raise ValueError(f"Provide the content or path for {name}.")


def _default_form_values() -> dict[str, str]:
    return {
        "mode": "optimize",
        "prompt_path": "prompt.txt",
        "benchmark_path": "benchmark.yaml",
        "config_path": "config.yaml",
        "prompt_content": "Classify the text below.\n\nInput:\n{input}",
        "benchmark_content": """name: dashboard-sample
version: v1
cases:
  - id: sample-001
    input: "customer promised to pay within 7 days"
    expected_output: "payment"
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
            verdict for verdict in filtered if case_id.lower() in verdict["test_case"]["id"].lower()
        ]
    if passed in {"true", "false"}:
        wanted = passed == "true"
        filtered = [verdict for verdict in filtered if bool(verdict.get("passed")) is wanted]
    if regression in {"true", "false"}:
        wanted = regression == "true"
        filtered = [verdict for verdict in filtered if bool(verdict.get("is_regression")) is wanted]
    if tag:
        filtered = [
            verdict for verdict in filtered if tag in verdict.get("test_case", {}).get("tags", [])
        ]
    if assertion_type:
        filtered = [
            verdict
            for verdict in filtered
            if verdict.get("test_case", {}).get("assertion", {}).get("type") == assertion_type
        ]
    if min_score is not None:
        filtered = [
            verdict for verdict in filtered if float(verdict.get("score", 0.0)) >= min_score
        ]
    if max_score is not None:
        filtered = [
            verdict for verdict in filtered if float(verdict.get("score", 0.0)) <= max_score
        ]
    return filtered


def _templates() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_WEB_ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["score"] = _score
    env.filters["money"] = _money
    env.filters["percent"] = _percent
    env.filters["stop_label"] = stop_reason_label
    env.filters["mode_label"] = run_mode_label
    env.filters["pretty_json"] = _pretty_json
    env.globals["model_label"] = _model_label
    env.globals["scorecard"] = _scorecard
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


def _scorecard(run: OptimizationRun, other: OptimizationRun | None = None) -> list[dict[str, Any]]:
    if not run.iterations or run.best_iteration is None:
        return []
    baseline = run.best_iteration if other is not None else run.iterations[0]
    selected = other.best_iteration if other is not None else run.best_iteration
    if selected is None:
        return []
    metrics = [
        ("Quality score", baseline.score, selected.score, "score", True),
        (
            "Pass rate",
            baseline.score_report.pass_rate,
            selected.score_report.pass_rate,
            "percent",
            True,
        ),
        (
            "Cost",
            baseline.score_report.operational.total_cost_usd,
            selected.score_report.operational.total_cost_usd,
            "money",
            False,
        ),
        (
            "p95 latency",
            baseline.score_report.operational.p95_latency_ms,
            selected.score_report.operational.p95_latency_ms,
            "latency",
            False,
        ),
    ]
    rows = []
    for label, before, after, unit, higher_is_better in metrics:
        delta = after - before
        scale = (
            100.0 if unit == "score" else 1.0 if unit == "percent" else max(before, after, 0.000001)
        )
        sign = "+" if delta > 0 else "−" if delta < 0 else ""
        magnitude = abs(delta)
        if unit == "money":
            before_text, after_text = _money(before), _money(after)
            delta_text = f"{sign}${magnitude:.4f}"
        elif unit == "latency":
            before_text, after_text = f"{before:.0f} ms", f"{after:.0f} ms"
            delta_text = f"{sign}{magnitude:.0f} ms"
        elif unit == "percent":
            before_text, after_text = _percent(before), _percent(after)
            delta_text = f"{sign}{magnitude * 100:.1f} pp"
        else:
            before_text, after_text = _score(before), _score(after)
            delta_text = f"{sign}{magnitude:.2f} pts"
        rows.append(
            {
                "label": label,
                "before": before_text,
                "after": after_text,
                "delta": delta,
                "delta_text": delta_text,
                "width": min(44.0, magnitude / scale * 44.0),
                "direction": "positive" if delta > 0 else "negative",
                "tone": "neutral"
                if delta == 0
                else "good"
                if (delta > 0) == higher_is_better
                else "bad",
            }
        )
    return rows
