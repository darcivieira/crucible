from __future__ import annotations

from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.application.optimizer import Optimizer
from crucible.modules.optimizer.application.reports import write_report
from crucible.modules.optimizer.domain.models import Gabarito, OptimizationConfig, Prompt


class CreateRunRequest(BaseModel):
    prompt: Prompt
    gabarito: Gabarito
    config: OptimizationConfig


class CreatedRun(BaseModel):
    task_id: str
    status: str


def create_api_app(store: SQLiteRunStore | None = None) -> FastAPI:
    settings = get_settings()
    run_store = store or SQLiteRunStore(settings.sqlite_path)
    app = FastAPI(title="Crucible API", version="0.1.0")

    @app.post("/runs", response_model=CreatedRun)
    async def create_run(
        request: CreateRunRequest, background_tasks: BackgroundTasks
    ) -> CreatedRun:
        task_id = uuid4().hex
        run_store.create_task(task_id, "queued")
        background_tasks.add_task(_run_optimization, task_id, request, run_store)
        return CreatedRun(task_id=task_id, status="queued")

    @app.get("/tasks/{task_id}")
    async def task_status(task_id: str) -> dict:
        try:
            return run_store.get_task(task_id).model_dump(mode="json")
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict:
        try:
            return run_store.request_task_cancel(task_id).model_dump(mode="json")
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.get("/runs")
    async def list_runs() -> list[dict]:
        return [summary.model_dump(mode="json") for summary in run_store.list_runs(limit=100)]

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return run.model_dump(mode="json")

    @app.post("/runs/{run_id}/reports/{format}")
    async def create_report(run_id: str, format: str) -> dict[str, str]:
        try:
            run = await run_store.load_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if format not in {"json", "html", "pdf"}:
            raise HTTPException(status_code=422, detail="Supported formats: json, html, pdf")
        path = write_report(run, settings.reports_dir, format)
        return {"path": str(path)}

    return app


async def _run_optimization(
    task_id: str,
    request: CreateRunRequest,
    store: SQLiteRunStore,
) -> None:
    store.update_task(task_id, "running")
    try:
        run = await Optimizer(
            request.config,
            store=store,
            should_cancel=lambda: store.task_cancel_requested(task_id),
        ).optimize(
            request.prompt, request.gabarito
        )
        if run.status == "aborted":
            store.update_task(task_id, "cancelled", run_id=run.id)
        else:
            store.update_task(task_id, "completed", run_id=run.id)
    except Exception as exc:
        store.update_task(task_id, "failed", error=str(exc))


def run_api(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(create_api_app(), host=host, port=port)
