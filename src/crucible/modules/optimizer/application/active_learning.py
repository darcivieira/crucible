from __future__ import annotations

from crucible.modules.optimizer.domain.models import ActiveLearningSuggestion, OptimizationRun


def suggest_cases(run: OptimizationRun, limit: int) -> list[ActiveLearningSuggestion]:
    if limit <= 0 or not run.iterations:
        return []

    latest = run.iterations[-1]
    candidates = []
    for verdict in latest.verdicts:
        run_detail = verdict.assertion_detail.get("runs", {})
        unstable = bool(run_detail.get("unstable", False))
        if verdict.passed and not unstable:
            continue
        reason_parts = []
        if not verdict.passed:
            reason_parts.append("failing_case")
        if verdict.is_regression:
            reason_parts.append("regression")
        if unstable:
            reason_parts.append("unstable_output")
        candidates.append(
            ActiveLearningSuggestion(
                test_case_id=verdict.test_case.id,
                input=verdict.test_case.input,
                expected_output_hint=verdict.test_case.expected_output,
                reason=",".join(reason_parts) or "low_confidence",
                tags=verdict.test_case.tags,
                score=verdict.score,
                unstable=unstable,
            )
        )

    candidates.sort(key=lambda item: (item.score, not item.unstable, item.test_case_id))
    return candidates[:limit]
