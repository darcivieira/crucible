from __future__ import annotations

from statistics import quantiles

from crucible.modules.optimizer.domain.models import OperationalMetrics, ScoreReport, Verdict


def aggregate_score(verdicts: list[Verdict]) -> ScoreReport:
    if not verdicts:
        return ScoreReport(global_score=0.0, pass_rate=0.0)

    total_weight = sum(verdict.test_case.weight for verdict in verdicts)
    weighted_sum = sum(verdict.score * verdict.test_case.weight for verdict in verdicts)
    global_score = (weighted_sum / total_weight) * 100

    return ScoreReport(
        global_score=global_score,
        pass_rate=sum(1 for verdict in verdicts if verdict.passed) / len(verdicts),
        by_tag=_group_by_tag(verdicts),
        by_assertion_type=_group_by_assertion(verdicts),
        worst_case_ids=[
            verdict.test_case.id for verdict in sorted(verdicts, key=lambda v: v.score)[:10]
        ],
        operational=OperationalMetrics(
            total_cost_usd=sum(verdict.execution.cost_usd for verdict in verdicts),
            p50_latency_ms=_percentile([verdict.execution.latency_ms for verdict in verdicts], 50),
            p95_latency_ms=_percentile([verdict.execution.latency_ms for verdict in verdicts], 95),
            total_tokens=sum(
                verdict.execution.tokens_in + verdict.execution.tokens_out for verdict in verdicts
            ),
        ),
    )


def _group_by_tag(verdicts: list[Verdict]) -> dict[str, float]:
    groups: dict[str, list[Verdict]] = {}
    for verdict in verdicts:
        for tag in verdict.test_case.tags or ["untagged"]:
            groups.setdefault(tag, []).append(verdict)
    return {tag: _weighted_score(items) for tag, items in groups.items()}


def _group_by_assertion(verdicts: list[Verdict]) -> dict[str, float]:
    groups: dict[str, list[Verdict]] = {}
    for verdict in verdicts:
        groups.setdefault(verdict.test_case.assertion.type, []).append(verdict)
    return {assertion_type: _weighted_score(items) for assertion_type, items in groups.items()}


def _weighted_score(verdicts: list[Verdict]) -> float:
    total_weight = sum(verdict.test_case.weight for verdict in verdicts)
    return (
        sum(verdict.score * verdict.test_case.weight for verdict in verdicts) / total_weight * 100
    )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    if percentile == 50:
        return quantiles(values, n=100, method="inclusive")[49]
    if percentile == 95:
        return quantiles(values, n=100, method="inclusive")[94]
    return sorted(values)[int((len(values) - 1) * percentile / 100)]
