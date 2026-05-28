from __future__ import annotations

import html
import json
from pathlib import Path

from crucible.modules.optimizer.domain.models import Iteration, OptimizationRun


def write_report(run: OptimizationRun, reports_dir: Path, format: str = "html") -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    if format == "json":
        path = reports_dir / f"{run.id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
        return path
    if format == "html":
        path = reports_dir / f"{run.id}.html"
        path.write_text(render_html_report(run), encoding="utf-8")
        return path
    if format == "pdf":
        from crucible.modules.optimizer.application.exports import export_report_pdf

        return export_report_pdf(run, reports_dir / f"{run.id}.pdf")
    raise ValueError(f"Unsupported report format: {format}")


def render_html_report(run: OptimizationRun) -> str:
    best = run.best_iteration
    target_model = _model_label(run.config.target_model) if run.config.target_model else "-"
    reasoning_model = (
        _model_label(run.config.reasoning_model) if run.config.reasoning_model else "-"
    )
    iteration_rows = "\n".join(
        (
            "<tr>"
            f"<td>v{iteration.version}</td>"
            f"<td>{iteration.score:.2f}</td>"
            f"<td>{iteration.score_report.pass_rate:.0%}</td>"
            f"<td>${iteration.score_report.operational.total_cost_usd:.4f}</td>"
            f"<td>{iteration.score_report.operational.p95_latency_ms:.0f}</td>"
            f"<td>{html.escape(_iteration_change(iteration))}</td>"
            "</tr>"
        )
        for iteration in run.iterations
    )
    worst_cases = best.score_report.worst_case_ids if best else []
    score_history = [iteration.score for iteration in run.iterations]
    task_contract = (
        json.dumps(run.task_contract.model_dump(mode="json"), indent=2, ensure_ascii=False)
        if run.task_contract
        else "{}"
    )
    comparison = _comparison_html(run)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Crucible report {html.escape(run.id)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; color: #1f2933; }}
    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px; text-align: left; }}
    th {{ background: #f0f4f8; }}
    pre {{ white-space: pre-wrap; background: #f8fafc; padding: 16px; border: 1px solid #d9e2ec; }}
    .metric {{ display: inline-block; margin-right: 24px; }}
  </style>
</head>
<body>
  <h1>Crucible Report</h1>
  <p><strong>Run:</strong> {html.escape(run.id)}</p>
  <p>
    <span class="metric"><strong>Status:</strong> {html.escape(run.status)}</span>
    <span class="metric"><strong>Stop:</strong> {html.escape(str(run.stop_reason))}</span>
    <span class="metric"><strong>Total cost:</strong> ${run.total_cost_usd:.4f}</span>
  </p>
  <p>
    <span class="metric"><strong>Target:</strong> {target_model}</span>
    <span class="metric"><strong>Reasoning:</strong> {reasoning_model}</span>
  </p>
  {comparison}
  <h2>Best Iteration</h2>
  <p><strong>Version:</strong> v{best.version if best else "n/a"} |
     <strong>Score:</strong> {best.score if best else 0:.2f}</p>
  <h2>Iterations</h2>
  <table>
    <thead>
      <tr>
        <th>Iteration</th><th>Score</th><th>Pass rate</th>
        <th>Cost</th><th>p95 ms</th><th>Change</th>
      </tr>
    </thead>
    <tbody>{iteration_rows}</tbody>
  </table>
  <h2>Score History</h2>
  <pre>{html.escape(json.dumps(score_history, indent=2))}</pre>
  <h2>Task Contract</h2>
  <pre>{html.escape(task_contract)}</pre>
  <h2>Worst Cases In Best Iteration</h2>
  <pre>{html.escape(json.dumps(worst_cases, indent=2))}</pre>
  <h2>Best Prompt</h2>
  <pre>{html.escape(best.prompt.template if best else "")}</pre>
</body>
</html>
"""


def _comparison_html(run: OptimizationRun) -> str:
    if run.comparison_summary is None:
        return ""
    summary = run.comparison_summary
    best_score = html.escape(str(summary.best_score.label))
    lowest_cost = html.escape(str(summary.lowest_cost.label))
    best_value = html.escape(str(summary.best_value.label))
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{html.escape(iteration.comparison_label or f'v{iteration.version}')}</td>"
            f"<td>{iteration.score:.2f}</td>"
            f"<td>{iteration.score_report.pass_rate:.0%}</td>"
            f"<td>${iteration.score_report.operational.total_cost_usd:.4f}</td>"
            f"<td>{iteration.score_report.operational.p95_latency_ms:.0f}</td>"
            f"<td>{iteration.score_report.operational.cached_tokens}</td>"
            "</tr>"
        )
        for iteration in run.iterations
    )
    return f"""
  <h2>Model Comparison</h2>
  <p>
    <span class="metric"><strong>Best score:</strong> {best_score}</span>
    <span class="metric"><strong>Lowest cost:</strong> {lowest_cost}</span>
    <span class="metric"><strong>Best value:</strong> {best_value}</span>
  </p>
  <table>
    <thead>
      <tr>
        <th>Model</th><th>Score</th><th>Pass rate</th>
        <th>Cost</th><th>p95 ms</th><th>Cached tokens</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
"""


def _model_label(model) -> str:
    return f"{html.escape(model.provider)}/{html.escape(model.model_id)}"


def _iteration_change(iteration: Iteration) -> str:
    change = iteration.diff_summary or ""
    if iteration.refinement_repair_attempts:
        repair_lines = [
            f"Repair attempt {attempt.attempt}: {', '.join(attempt.violations)}"
            for attempt in iteration.refinement_repair_attempts
        ]
        change = f"{change}\n" + "\n".join(repair_lines)
    if iteration.refinement_rejected_reason:
        change = f"{change}\nRejected refinement: {iteration.refinement_rejected_reason}".strip()
    return change
