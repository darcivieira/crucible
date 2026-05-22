from __future__ import annotations

import asyncio
import difflib
import json
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
import yaml
from rich.console import Console
from rich.table import Table

from crucible.core.logging import configure_logging
from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.importers import import_gabarito
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.application.estimates import estimate_cost as estimate_cost_for
from crucible.modules.optimizer.application.exports import export_run
from crucible.modules.optimizer.application.optimizer import Optimizer
from crucible.modules.optimizer.application.reports import write_report
from crucible.modules.optimizer.domain.models import Gabarito, OptimizationConfig, Prompt
from crucible.modules.optimizer.plugins.registry import load_plugins
from crucible.modules.optimizer.presentation.api.app import create_api_app
from crucible.modules.optimizer.presentation.web.app import create_dashboard_app

app = typer.Typer(help="Crucible prompt optimization CLI.")
console = Console()


@app.callback()
def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    if settings.plugin_modules:
        load_plugins([item.strip() for item in settings.plugin_modules.split(",") if item.strip()])


@app.command()
def init(path: Annotated[Path, typer.Argument(help="Project directory to initialize.")]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "prompt.txt").write_text(
        "Responda ao input abaixo de forma objetiva.\n\nInput:\n{input}\n",
        encoding="utf-8",
    )
    (path / "gabarito.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "sample",
                "version": "v1",
                "cases": [
                    {
                        "id": "case-001",
                        "input": "Diga apenas: ok",
                        "expected_output": "ok",
                        "assertion": {"type": "contains"},
                        "weight": 1.0,
                        "tags": ["smoke"],
                    }
                ],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "threshold": 95.0,
                "max_iterations": 3,
                "max_cost_usd": 5.0,
                "parallelism": 2,
                "target_model": {
                    "provider": "ollama",
                    "model_id": "gemma3:4b",
                    "role": "target",
                    "params": {"temperature": 0.0, "max_tokens": 1024},
                },
                "reasoning_model": {
                    "provider": "openai",
                    "model_id": "gpt-5",
                    "role": "reasoning",
                    "params": {"temperature": 0.0, "max_tokens": 2048},
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    console.print(f"Initialized Crucible project at {path}")


@app.command()
def validate(
    prompt: Annotated[Path, typer.Option("--prompt", "-p")],
    gabarito: Annotated[Path, typer.Option("--gabarito", "-g")],
    config: Annotated[Path, typer.Option("--config", "-c")],
) -> None:
    iteration = asyncio.run(
        Optimizer(_load_config(config)).validate(_load_prompt(prompt), _load_gabarito(gabarito))
    )
    _print_iterations([iteration])


@app.command()
def optimize(
    config: Annotated[Path, typer.Option("--config", "-c")],
    prompt: Annotated[Path | None, typer.Option("--prompt", "-p")] = None,
    gabarito: Annotated[Path | None, typer.Option("--gabarito", "-g")] = None,
) -> None:
    config_dir = config.parent
    prompt_path = prompt or config_dir / "prompt.txt"
    gabarito_path = gabarito or config_dir / "gabarito.yaml"
    run = asyncio.run(
        Optimizer(_load_config(config)).optimize(
            _load_prompt(prompt_path), _load_gabarito(gabarito_path)
        )
    )
    _print_iterations(run.iterations)
    best = run.best_iteration
    report_path = write_report(run, get_settings().reports_dir, "html")
    console.print(
        f"Run {run.id} completed: stop_reason={run.stop_reason}, "
        f"best=v{best.version if best else 'n/a'} score={best.score if best else 0:.2f}"
    )
    console.print(f"Report: {report_path}")


@app.command()
def diff(
    run: Annotated[str, typer.Option("--run")],
    from_version: Annotated[int, typer.Option("--from")] = 0,
    to: Annotated[str, typer.Option("--to")] = "best",
) -> None:
    loaded = asyncio.run(_store().load_run(run))
    left = loaded.iterations[from_version]
    if to == "best":
        right = loaded.best_iteration
        if right is None:
            raise typer.BadParameter("Run has no best iteration")
    else:
        right = loaded.iterations[int(to.removeprefix("v"))]
    console.print(
        "\n".join(
            difflib.unified_diff(
                left.prompt.template.splitlines(),
                right.prompt.template.splitlines(),
                fromfile=f"v{left.version}",
                tofile=f"v{right.version}",
                lineterm="",
            )
        )
    )


@app.command()
def report(
    run: Annotated[str, typer.Option("--run")],
    format: Annotated[str, typer.Option("--format")] = "html",
) -> None:
    if format not in {"json", "html", "pdf"}:
        raise typer.BadParameter("Supported formats: json, html, pdf")
    loaded = asyncio.run(_store().load_run(run))
    path = write_report(loaded, get_settings().reports_dir, format)
    if format == "json":
        console.print_json(path.read_text(encoding="utf-8"))
    else:
        console.print(str(path))


@app.command()
def export(
    run: Annotated[str, typer.Option("--run")],
    format: Annotated[str, typer.Option("--format")],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    if format not in {"csv", "parquet", "prompt", "pdf"}:
        raise typer.BadParameter("Supported formats: csv, parquet, prompt, pdf")
    loaded = asyncio.run(_store().load_run(run))
    console.print(str(export_run(loaded, output, format)))


@app.command("import-gabarito")
def import_gabarito_command(
    source: Annotated[str, typer.Option("--source")],
    input_path: Annotated[Path, typer.Option("--input", "-i")],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    gabarito = import_gabarito(input_path, source)
    output.write_text(
        yaml.safe_dump(gabarito.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    console.print(str(output))


@app.command("list-runs")
def list_runs(limit: Annotated[int, typer.Option("--limit", "-n")] = 20) -> None:
    table = Table(title="Crucible Runs")
    table.add_column("Run")
    table.add_column("Status")
    table.add_column("Best", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Target")
    table.add_column("Started")
    for summary in _store().list_runs(limit=limit):
        table.add_row(
            summary.id,
            summary.status,
            f"{summary.best_score:.2f}" if summary.best_score is not None else "-",
            f"${summary.total_cost_usd:.4f}",
            summary.target_model,
            summary.started_at,
        )
    console.print(table)


@app.command("show-run")
def show_run(run: Annotated[str, typer.Option("--run")] = "latest") -> None:
    loaded = asyncio.run(_store().load_run(run))
    best = loaded.best_iteration
    console.print_json(
        json.dumps(
            {
                "run_id": loaded.id,
                "status": loaded.status,
                "stop_reason": loaded.stop_reason,
                "iterations": len(loaded.iterations),
                "best_version": best.version if best else None,
                "best_score": best.score if best else None,
                "total_cost_usd": loaded.total_cost_usd,
                "target_model": loaded.config.target_model.model_dump(mode="json"),
                "reasoning_model": loaded.config.reasoning_model.model_dump(mode="json"),
            }
        )
    )


@app.command("compare-runs")
def compare_runs(
    left: Annotated[str, typer.Argument()],
    right: Annotated[str, typer.Argument()],
) -> None:
    left_run = asyncio.run(_store().load_run(left))
    right_run = asyncio.run(_store().load_run(right))
    left_best = left_run.best_iteration
    right_best = right_run.best_iteration
    table = Table(title="Run Comparison")
    table.add_column("Metric")
    table.add_column(left_run.id)
    table.add_column(right_run.id)
    table.add_row(
        "Best score",
        f"{left_best.score:.2f}" if left_best else "-",
        f"{right_best.score:.2f}" if right_best else "-",
    )
    table.add_row("Iterations", str(len(left_run.iterations)), str(len(right_run.iterations)))
    table.add_row("Cost", f"${left_run.total_cost_usd:.4f}", f"${right_run.total_cost_usd:.4f}")
    table.add_row("Stop reason", str(left_run.stop_reason), str(right_run.stop_reason))
    console.print(table)


@app.command("estimate-cost")
def estimate_cost(
    config: Annotated[Path, typer.Option("--config", "-c")],
    prompt: Annotated[Path | None, typer.Option("--prompt", "-p")] = None,
    gabarito: Annotated[Path | None, typer.Option("--gabarito", "-g")] = None,
) -> None:
    config_dir = config.parent
    loaded_config = _load_config(config)
    prompt_path = prompt or config_dir / "prompt.txt"
    gabarito_path = gabarito or config_dir / "gabarito.yaml"
    estimate = estimate_cost_for(
        _load_prompt(prompt_path),
        _load_gabarito(gabarito_path),
        loaded_config,
    )
    console.print_json(estimate.model_dump_json())


@app.command("split-gabarito")
def split_gabarito(
    gabarito: Annotated[Path, typer.Option("--gabarito", "-g")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")],
    train: Annotated[float, typer.Option("--train")] = 0.7,
    val: Annotated[float, typer.Option("--val")] = 0.15,
) -> None:
    loaded = _load_gabarito(gabarito)
    train_set, val_set, test_set = loaded.split(train=train, val=val)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, split in [("train", train_set), ("val", val_set), ("test", test_set)]:
        (output_dir / f"gabarito.{name}.yaml").write_text(
            yaml.safe_dump(split.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    console.print(f"Wrote split gabaritos to {output_dir}")


@app.command()
def serve(
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
) -> None:
    settings = get_settings()
    bind_host = host or settings.dashboard_host
    bind_port = port or settings.dashboard_port
    console.print(f"Serving Crucible dashboard at http://{bind_host}:{bind_port}")
    uvicorn.run(create_dashboard_app(), host=bind_host, port=bind_port)


@app.command()
def api(
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int, typer.Option("--port")] = 7788,
) -> None:
    settings = get_settings()
    bind_host = host or settings.dashboard_host
    console.print(f"Serving Crucible API at http://{bind_host}:{port}")
    uvicorn.run(create_api_app(), host=bind_host, port=port)


def _load_prompt(path: Path) -> Prompt:
    template = path.read_text(encoding="utf-8")
    return Prompt(template=template, variables=["input"] if "{input}" in template else [])


def _load_gabarito(path: Path) -> Gabarito:
    if path.suffix.lower() == ".json":
        return Gabarito.from_json(path)
    return Gabarito.from_yaml(path)


def _load_config(path: Path) -> OptimizationConfig:
    with path.open(encoding="utf-8") as file:
        return OptimizationConfig.model_validate(yaml.safe_load(file))


def _store() -> SQLiteRunStore:
    return SQLiteRunStore(get_settings().sqlite_path)


def _print_iterations(iterations: list) -> None:
    table = Table(title="Crucible Run")
    table.add_column("Iter")
    table.add_column("Score", justify="right")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("p95 ms", justify="right")
    for iteration in iterations:
        table.add_row(
            f"v{iteration.version}",
            f"{iteration.score:.2f}",
            f"{iteration.score_report.pass_rate:.0%}",
            f"${iteration.score_report.operational.total_cost_usd:.4f}",
            f"{iteration.score_report.operational.p95_latency_ms:.0f}",
        )
    console.print(table)
