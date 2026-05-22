from __future__ import annotations

from crucible.modules.optimizer.domain.models import Iteration, OptimizationRun


def update_multi_objective(run: OptimizationRun) -> None:
    if not run.iterations:
        run.pareto_frontier_versions = []
        return

    max_cost = max(
        (iteration.score_report.operational.total_cost_usd for iteration in run.iterations),
        default=0.0,
    )
    max_latency = max(
        (iteration.score_report.operational.p95_latency_ms for iteration in run.iterations),
        default=0.0,
    )

    for iteration in run.iterations:
        iteration.objective_score = _objective_score(iteration, run, max_cost, max_latency)
        iteration.pareto_dominated = _is_dominated(iteration, run.iterations)

    run.pareto_frontier_versions = [
        iteration.version for iteration in run.iterations if not iteration.pareto_dominated
    ]


def _objective_score(
    iteration: Iteration,
    run: OptimizationRun,
    max_cost: float,
    max_latency: float,
) -> float:
    quality = iteration.score / 100
    cost_penalty = (
        iteration.score_report.operational.total_cost_usd / max_cost if max_cost > 0 else 0.0
    )
    latency_penalty = (
        iteration.score_report.operational.p95_latency_ms / max_latency if max_latency > 0 else 0.0
    )
    return (
        quality * run.config.objective_quality_weight
        - cost_penalty * run.config.objective_cost_weight
        - latency_penalty * run.config.objective_latency_weight
    )


def _is_dominated(candidate: Iteration, iterations: list[Iteration]) -> bool:
    candidate_cost = candidate.score_report.operational.total_cost_usd
    candidate_latency = candidate.score_report.operational.p95_latency_ms
    for other in iterations:
        if other.version == candidate.version:
            continue
        other_cost = other.score_report.operational.total_cost_usd
        other_latency = other.score_report.operational.p95_latency_ms
        at_least_as_good = (
            other.score >= candidate.score
            and other_cost <= candidate_cost
            and other_latency <= candidate_latency
        )
        strictly_better = (
            other.score > candidate.score
            or other_cost < candidate_cost
            or other_latency < candidate_latency
        )
        if at_least_as_good and strictly_better:
            return True
    return False
