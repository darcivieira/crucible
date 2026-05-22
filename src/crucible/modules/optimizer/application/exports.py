from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crucible.modules.optimizer.application.reports import render_html_report
from crucible.modules.optimizer.domain.models import OptimizationRun


def export_run(run: OptimizationRun, output: Path, format: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if format == "csv":
        return export_verdicts_csv(run, output)
    if format == "parquet":
        return export_verdicts_parquet(run, output)
    if format == "prompt":
        return export_best_prompt(run, output)
    if format == "pdf":
        return export_report_pdf(run, output)
    raise ValueError(f"Unsupported export format: {format}")


def export_verdicts_csv(run: OptimizationRun, output: Path) -> Path:
    rows = _verdict_rows(run)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()) if rows else _fields())
        writer.writeheader()
        writer.writerows(rows)
    return output


def export_verdicts_parquet(run: OptimizationRun, output: Path) -> Path:
    rows = _verdict_rows(run)
    table = pa.Table.from_pylist(rows or [{field: None for field in _fields()}])
    pq.write_table(table, output)
    return output


def export_best_prompt(run: OptimizationRun, output: Path) -> Path:
    best = run.best_iteration
    output.write_text(best.prompt.template if best else "", encoding="utf-8")
    return output


def export_report_pdf(run: OptimizationRun, output: Path) -> Path:
    text = _plain_text(render_html_report(run))
    output.write_bytes(_minimal_pdf(text))
    return output


def _verdict_rows(run: OptimizationRun) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for iteration in run.iterations:
        for verdict in iteration.verdicts:
            rows.append(
                {
                    "run_id": run.id,
                    "iteration": iteration.version,
                    "test_case_id": verdict.test_case.id,
                    "score": verdict.score,
                    "passed": verdict.passed,
                    "is_regression": verdict.is_regression,
                    "latency_ms": verdict.execution.latency_ms,
                    "tokens_in": verdict.execution.tokens_in,
                    "tokens_out": verdict.execution.tokens_out,
                    "cost_usd": verdict.execution.cost_usd,
                    "tags": ",".join(verdict.test_case.tags),
                    "assertion_type": verdict.test_case.assertion.type,
                }
            )
    return rows


def _fields() -> list[str]:
    return [
        "run_id",
        "iteration",
        "test_case_id",
        "score",
        "passed",
        "is_regression",
        "latency_ms",
        "tokens_in",
        "tokens_out",
        "cost_usd",
        "tags",
        "assertion_type",
    ]


def _plain_text(html: str) -> str:
    text = html.replace("<", "\n<")
    lines = [line for line in text.splitlines() if not line.strip().startswith("<")]
    return "\n".join(line.strip() for line in lines if line.strip())


def _minimal_pdf(text: str) -> bytes:
    safe_lines = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in text.splitlines()
    ]
    body = ["BT", "/F1 10 Tf", "40 800 Td"]
    for line in safe_lines[:80]:
        body.append(f"({line[:100]}) Tj")
        body.append("0 -14 Td")
    body.append("ET")
    stream = "\n".join(body).encode()
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        b"5 0 obj << /Length "
        + str(len(stream)).encode()
        + b" >> stream\n"
        + stream
        + b"\nendstream endobj",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content.extend(obj + b"\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        f"trailer << /Root 1 0 R /Size {len(objects) + 1} >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(content)
