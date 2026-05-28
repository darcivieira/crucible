from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.application.contracts import build_task_contract
from crucible.modules.optimizer.application.optimizer import Optimizer
from crucible.modules.optimizer.domain.models import (
    Gabarito,
    OptimizationConfig,
    OptimizationRun,
    Prompt,
    RunMode,
)


class RunTaskRequest(BaseModel):
    prompt: Prompt
    gabarito: Gabarito
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
        store.update_task(task_id, "failed", error=str(exc))


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
        return await validate_as_run(optimizer, request.prompt, request.gabarito, store)
    if request.mode == "compare":
        return await optimizer.compare_models(request.prompt, request.gabarito)
    return await optimizer.optimize(request.prompt, request.gabarito)


async def validate_as_run(
    optimizer: Optimizer,
    prompt: Prompt,
    gabarito: Gabarito,
    store: SQLiteRunStore,
) -> OptimizationRun:
    started_at = datetime.now(UTC)
    iteration = await optimizer.validate(prompt, gabarito)
    run = OptimizationRun(
        run_mode="validate",
        config=optimizer.config,
        task_contract=build_task_contract(prompt, gabarito, optimizer.config),
        gabarito_hash=gabarito.content_hash,
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
        "threshold_reached": "Objetivo atingido",
        "max_iterations": "Limite de iterações",
        "budget_exhausted": "Budget atingido",
        "time_exhausted": "Tempo esgotado",
        "plateau": "Parou de melhorar",
        "no_failures": "Sem falhas",
        "cancelled": "Cancelado",
        "validation_only": "Validação executada",
        "reasoning_failed_to_refine": "Reasoning não gerou prompt válido",
        "comparison_completed": "Comparação concluída",
        None: "Em andamento",
    }
    return labels.get(reason, str(reason))


def next_step_hint(
    stop_reason: str | None,
    best_score: float | None,
    pass_rate: float | None,
) -> str:
    if stop_reason == "threshold_reached":
        return "Revise worst cases e custo antes de promover o prompt."
    if stop_reason == "validation_only":
        return "Se o score estiver baixo, rode optimize ou ajuste gabarito/assertions."
    if stop_reason == "comparison_completed":
        return "Compare os vencedores por score, custo e custo-benefício antes de promover."
    if stop_reason == "plateau":
        return "Analise regressões e considere novos exemplos ou uma rubrica mais objetiva."
    if stop_reason == "max_iterations":
        return "Aumente iterações apenas se as últimas versões ainda estiverem melhorando."
    if stop_reason == "budget_exhausted":
        return "Reduza casos, concorrência ou use um modelo mais barato para investigar."
    if stop_reason == "cancelled":
        return "Confira a última iteração salva antes de retomar a execução."
    if stop_reason == "reasoning_failed_to_refine":
        return (
            "Revise as tentativas de reparo: o modelo reasoning não conseguiu "
            "preservar o contrato."
        )
    if best_score is not None and best_score < 50:
        return "Comece pelos worst cases: o prompt provavelmente ainda não capturou o contrato."
    if pass_rate is not None and pass_rate < 0.8:
        return "Score parcial existe, mas muitos casos ainda não passam completamente."
    return "Compare a melhor versão com v0 e inspecione falhas restantes."
