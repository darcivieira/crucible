from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.application.contracts import build_task_contract
from crucible.modules.optimizer.application.optimizer import Optimizer
from crucible.modules.optimizer.domain.models import (
    Benchmark,
    OptimizationConfig,
    OptimizationRun,
    Prompt,
    RunMode,
)


class RunTaskRequest(BaseModel):
    prompt: Prompt
    benchmark: Benchmark
    config: OptimizationConfig
    mode: RunMode = "optimize"


async def run_task(
    task_id: str,
    request: RunTaskRequest,
    store: SQLiteRunStore,
) -> None:
    store.update_task(task_id, "running")
    try:
        run = await execute_run_request(task_id, request, store)
        if run.status == "aborted":
            store.update_task(task_id, "cancelled", run_id=run.id)
        else:
            store.update_task(task_id, "completed", run_id=run.id)
    except Exception as exc:
        run_id = getattr(exc, "run_id", None) or _latest_failed_run_id(store)
        store.update_task(task_id, "failed", run_id=run_id, error=str(exc))


async def execute_run_request(
    task_id: str,
    request: RunTaskRequest,
    store: SQLiteRunStore,
) -> OptimizationRun:
    optimizer = Optimizer(
        request.config,
        store=store,
        should_cancel=lambda: store.task_cancel_requested(task_id),
    )
    if request.mode == "validate":
        return await validate_as_run(optimizer, request.prompt, request.benchmark, store)
    if request.mode == "compare":
        return await optimizer.compare_models(request.prompt, request.benchmark)
    return await optimizer.optimize(request.prompt, request.benchmark)


async def validate_as_run(
    optimizer: Optimizer,
    prompt: Prompt,
    benchmark: Benchmark,
    store: SQLiteRunStore,
) -> OptimizationRun:
    started_at = datetime.now(UTC)
    iteration = await optimizer.validate(prompt, benchmark)
    run = OptimizationRun(
        run_mode="validate",
        config=optimizer.config,
        task_contract=build_task_contract(prompt, benchmark, optimizer.config),
        benchmark_hash=benchmark.content_hash,
        initial_prompt_hash=prompt.content_hash,
        iterations=[iteration],
        status="completed",
        stop_reason="validation_only",
        provider_cache_warnings=optimizer.provider_cache_warnings,
        started_at=started_at,
        ended_at=datetime.now(UTC),
    )
    await store.save_run(run)
    return run


def _latest_failed_run_id(store: SQLiteRunStore) -> str | None:
    for summary in store.list_runs(limit=5):
        if summary.status == "failed":
            return summary.id
    return None


def run_mode_label(mode: str | None) -> str:
    labels: dict[str | None, str] = {
        "validate": "Validate",
        "optimize": "Optimize",
        "compare": "Compare",
        None: "Optimize",
    }
    return labels.get(mode, str(mode))


def stop_reason_label(reason: str | None) -> str:
    labels: dict[str | None, str] = {
        "threshold_reached": "Target reached",
        "max_iterations": "Iteration limit",
        "budget_exhausted": "Budget reached",
        "time_exhausted": "Time limit reached",
        "plateau": "No further improvement",
        "no_failures": "No failures",
        "cancelled": "Cancelled",
        "validation_only": "Validation completed",
        "reasoning_failed_to_refine": "Reasoning model did not produce a valid prompt",
        "comparison_completed": "Comparison completed",
        None: "In progress",
    }
    return labels.get(reason, str(reason))


def next_step_hint(
    stop_reason: str | None,
    best_score: float | None,
    pass_rate: float | None,
) -> str:
    if stop_reason == "threshold_reached":
        return "Review the worst cases and cost before promoting the prompt."
    if stop_reason == "validation_only":
        return "If the score is low, run optimize or adjust the benchmark/assertions."
    if stop_reason == "comparison_completed":
        return "Compare the winners by score, cost, and value before promoting a model."
    if stop_reason == "plateau":
        return "Analyze regressions and consider new examples or a more objective rubric."
    if stop_reason == "max_iterations":
        return "Increase iterations only if the latest versions are still improving."
    if stop_reason == "budget_exhausted":
        return "Reduce cases or concurrency, or use a cheaper model to investigate."
    if stop_reason == "cancelled":
        return "Check the last saved iteration before resuming execution."
    if stop_reason == "reasoning_failed_to_refine":
        return "Review the repair attempts: the reasoning model could not preserve the contract."
    if best_score is not None and best_score < 50:
        return "Start with the worst cases: the prompt probably has not captured the contract yet."
    if pass_rate is not None and pass_rate < 0.8:
        return "Partial scores exist, but many cases still do not pass completely."
    return "Compare the best version with v0 and inspect the remaining failures."
