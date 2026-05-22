import yaml
from typer.testing import CliRunner

from crucible import Contains, ModelSpec, OptimizationConfig, Prompt
from crucible import TestCase as CrucibleTestCase
from crucible.modules.optimizer.domain.models import (
    ExecutionResult,
    Iteration,
    OptimizationRun,
    Verdict,
)
from crucible.modules.optimizer.domain.scoring import aggregate_score
from crucible.modules.optimizer.presentation.cli.app import app


def test_init_creates_project_files(tmp_path):
    runner = CliRunner()
    project = tmp_path / "sample"

    result = runner.invoke(app, ["init", str(project)])

    assert result.exit_code == 0
    assert (project / "prompt.txt").exists()
    assert (project / "gabarito.yaml").exists()
    assert (project / "config.yaml").exists()


def test_validate_runs_with_fake_provider(tmp_path):
    runner = CliRunner()
    prompt = tmp_path / "prompt.txt"
    gabarito = tmp_path / "gabarito.yaml"
    config = tmp_path / "config.yaml"
    prompt.write_text("{input}", encoding="utf-8")
    gabarito.write_text(
        yaml.safe_dump(
            {
                "name": "sample",
                "version": "v1",
                "cases": [
                    {
                        "id": "case-1",
                        "input": "ok",
                        "expected_output": "ok",
                        "assertion": {"type": "contains"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        yaml.safe_dump(
            {
                "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
                "reasoning_model": {
                    "provider": "fake",
                    "model_id": "reasoning",
                    "role": "reasoning",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "validate",
            "--prompt",
            str(prompt),
            "--gabarito",
            str(gabarito),
            "--config",
            str(config),
        ],
    )

    assert result.exit_code == 0
    assert "100.00" in result.output


def test_report_and_diff_commands_load_saved_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUCIBLE_SQLITE_PATH", str(tmp_path / "crucible.sqlite"))
    monkeypatch.setenv("CRUCIBLE_REPORTS_DIR", str(tmp_path / "reports"))
    from crucible.core import settings as settings_module

    settings_module._settings = None
    run = _saved_run(tmp_path / "crucible.sqlite")
    runner = CliRunner()

    report_result = runner.invoke(app, ["report", "--run", run.id, "--format", "html"])
    diff_result = runner.invoke(app, ["diff", "--run", run.id, "--from", "0", "--to", "best"])

    assert report_result.exit_code == 0
    assert (tmp_path / "reports" / f"{run.id}.html").exists()
    assert diff_result.exit_code == 0
    assert "+novo {input}" in diff_result.output


def test_history_estimate_and_split_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUCIBLE_SQLITE_PATH", str(tmp_path / "crucible.sqlite"))
    from crucible.core import settings as settings_module

    settings_module._settings = None
    run = _saved_run(tmp_path / "crucible.sqlite")
    prompt, gabarito, config = _write_project_files(tmp_path)
    runner = CliRunner()

    list_result = runner.invoke(app, ["list-runs"])
    show_result = runner.invoke(app, ["show-run", "--run", "latest"])
    compare_result = runner.invoke(app, ["compare-runs", run.id, run.id])
    estimate_result = runner.invoke(
        app,
        [
            "estimate-cost",
            "--prompt",
            str(prompt),
            "--gabarito",
            str(gabarito),
            "--config",
            str(config),
        ],
    )
    split_dir = tmp_path / "splits"
    split_result = runner.invoke(
        app,
        ["split-gabarito", "--gabarito", str(gabarito), "--output-dir", str(split_dir)],
    )

    assert list_result.exit_code == 0
    assert "fake/t" in list_result.output
    assert show_result.exit_code == 0
    assert run.id in show_result.output
    assert compare_result.exit_code == 0
    assert "Best score" in compare_result.output
    assert estimate_result.exit_code == 0
    assert "estimated_total_cost_usd" in estimate_result.output
    assert split_result.exit_code == 0
    assert (split_dir / "gabarito.train.yaml").exists()


def test_export_and_import_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUCIBLE_SQLITE_PATH", str(tmp_path / "crucible.sqlite"))
    from crucible.core import settings as settings_module

    settings_module._settings = None
    run = _saved_run(tmp_path / "crucible.sqlite")
    runner = CliRunner()
    csv_path = tmp_path / "verdicts.csv"
    parquet_path = tmp_path / "verdicts.parquet"
    pdf_path = tmp_path / "report.pdf"
    prompt_path = tmp_path / "best.txt"
    jsonl_path = tmp_path / "cases.jsonl"
    imported_path = tmp_path / "imported.yaml"
    jsonl_path.write_text(
        '{"id": "case", "input": "hello", "expected_output": "world"}\n',
        encoding="utf-8",
    )

    csv_result = runner.invoke(
        app, ["export", "--run", run.id, "--format", "csv", "-o", str(csv_path)]
    )
    parquet_result = runner.invoke(
        app, ["export", "--run", run.id, "--format", "parquet", "-o", str(parquet_path)]
    )
    pdf_result = runner.invoke(
        app, ["export", "--run", run.id, "--format", "pdf", "-o", str(pdf_path)]
    )
    prompt_result = runner.invoke(
        app, ["export", "--run", run.id, "--format", "prompt", "-o", str(prompt_path)]
    )
    import_result = runner.invoke(
        app,
        [
            "import-gabarito",
            "--source",
            "jsonl",
            "-i",
            str(jsonl_path),
            "-o",
            str(imported_path),
        ],
    )

    assert csv_result.exit_code == 0
    assert parquet_result.exit_code == 0
    assert pdf_result.exit_code == 0
    assert prompt_result.exit_code == 0
    assert import_result.exit_code == 0
    assert csv_path.exists()
    assert parquet_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert "novo" in prompt_path.read_text(encoding="utf-8")
    assert imported_path.exists()


def test_serve_command_starts_dashboard(monkeypatch):
    called = {}

    def fake_run(app_obj, host, port):
        called["app"] = app_obj
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr("crucible.modules.optimizer.presentation.cli.app.uvicorn.run", fake_run)

    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9999"])

    assert result.exit_code == 0
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 9999


def _saved_run(root):
    import asyncio

    from crucible.modules.optimizer.adapters.storage import SQLiteRunStore

    case = CrucibleTestCase(id="case", input="ok", expected_output="ok", assertion=Contains())
    first_verdict = Verdict(
        test_case=case,
        execution=ExecutionResult(test_case_id="case", actual_output="wrong", latency_ms=1),
        score=0,
        passed=False,
    )
    second_verdict = Verdict(
        test_case=case,
        execution=ExecutionResult(test_case_id="case", actual_output="ok", latency_ms=1),
        score=1,
        passed=True,
    )
    config = OptimizationConfig(
        target_model=ModelSpec(provider="fake", model_id="t", role="target"),
        reasoning_model=ModelSpec(provider="fake", model_id="r", role="reasoning"),
    )
    run = OptimizationRun(config=config, gabarito_hash="g", initial_prompt_hash="p")
    run.iterations.extend(
        [
            Iteration(
                version=0,
                prompt=Prompt(template="velho {input}", variables=["input"]),
                verdicts=[first_verdict],
                score_report=aggregate_score([first_verdict]),
            ),
            Iteration(
                version=1,
                prompt=Prompt(template="novo {input}", variables=["input"]),
                verdicts=[second_verdict],
                score_report=aggregate_score([second_verdict]),
            ),
        ]
    )
    asyncio.run(SQLiteRunStore(root).save_run(run))
    return run


def _write_project_files(root):
    prompt = root / "prompt.txt"
    gabarito = root / "gabarito.yaml"
    config = root / "config.yaml"
    prompt.write_text("{input}", encoding="utf-8")
    gabarito.write_text(
        yaml.safe_dump(
            {
                "name": "sample",
                "version": "v1",
                "cases": [
                    {
                        "id": f"case-{index}",
                        "input": "ok",
                        "expected_output": "ok",
                        "assertion": {"type": "contains"},
                    }
                    for index in range(3)
                ],
            }
        ),
        encoding="utf-8",
    )
    config.write_text(
        yaml.safe_dump(
            {
                "max_iterations": 2,
                "target_model": {
                    "provider": "fake",
                    "model_id": "target",
                    "role": "target",
                    "cost_per_million_input_tokens_usd": 1.0,
                    "cost_per_million_output_tokens_usd": 2.0,
                },
                "reasoning_model": {
                    "provider": "fake",
                    "model_id": "reasoning",
                    "role": "reasoning",
                    "cost_per_million_input_tokens_usd": 3.0,
                    "cost_per_million_output_tokens_usd": 4.0,
                },
            }
        ),
        encoding="utf-8",
    )
    return prompt, gabarito, config
