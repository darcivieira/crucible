import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from crucible import Benchmark, Gabarito, ModelSpec, OptimizationConfig, Optimizer, Prompt
from crucible import TestCase as CrucibleTestCase
from crucible.core import settings as settings_module
from crucible.core.settings import Settings
from crucible.modules.optimizer.adapters.storage import FileRunStore, SQLiteRunStore
from crucible.modules.optimizer.application.contracts import (
    build_task_contract,
    validate_refinement_against_contract,
)
from crucible.modules.optimizer.domain.models import (
    ContractRule,
    OptimizationRun,
    RefinementProposal,
)
from crucible.modules.optimizer.presentation.api.app import create_api_app
from crucible.modules.optimizer.presentation.cli.app import app
from crucible.modules.optimizer.presentation.web.app import create_dashboard_app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_settings",
        Settings(
            _env_file=None,
            runs_dir=tmp_path / "runs",
            cache_dir=tmp_path / "cache",
            reports_dir=tmp_path / "reports",
            sqlite_path=tmp_path / "runs.sqlite",
        ),
    )


def _config(**updates):
    return OptimizationConfig(
        target_model=ModelSpec(provider="fake", model_id="target", role="target"),
        reasoning_model=ModelSpec(provider="fake", model_id="reasoning", role="reasoning"),
        **updates,
    )


def _benchmark(count=1):
    return Benchmark(
        name="compatibility",
        version="v1",
        cases=[
            CrucibleTestCase(
                id=f"case-{index}",
                input="ok",
                expected_output="ok",
                assertion={"type": "contains"},
            )
            for index in range(count)
        ],
    )


def _proposal(text):
    return RefinementProposal(
        new_prompt=text,
        diff_summary="rewords the task",
        rationale="preserves existing task behavior",
        confidence=0.9,
    )


def test_legacy_sdk_model_and_config_aliases():
    assert Gabarito is Benchmark
    config = OptimizationConfig.model_validate({"use_gabarito_split": True})
    assert config.use_benchmark_split is True
    assert config.use_gabarito_split is True
    config.use_gabarito_split = False
    assert config.use_benchmark_split is False
    assert config.model_dump()["use_gabarito_split"] is False


@pytest.mark.asyncio
async def test_legacy_sdk_keywords_execute_validation_optimization_and_estimation():
    optimizer = Optimizer(_config())
    prompt = Prompt(template="{input}", variables=["input"])
    benchmark = _benchmark()
    iteration = await optimizer.validate(prompt, gabarito=benchmark)
    run = await optimizer.optimize(prompt, gabarito=benchmark)
    estimate = optimizer.estimate_cost(prompt, gabarito=benchmark)
    assert iteration.score == 100
    assert run.best_iteration.score == 100
    assert run.stop_reason == "threshold_reached"
    assert estimate.cases_count == 1


@pytest.mark.asyncio
async def test_legacy_split_configuration_is_applied_during_optimization():
    config = _config()
    config.use_gabarito_split = True
    run = await Optimizer(config).optimize(Prompt(template="{input}"), gabarito=_benchmark(8))
    assert len(run.iterations[0].verdicts) == 5
    assert run.validation_scores == {"train": 100, "val": 100, "test": 100, "train_val_gap": 0}


@pytest.mark.asyncio
async def test_legacy_run_payload_loads_from_files_and_sqlite_without_rewriting(tmp_path):
    run = await Optimizer(_config()).optimize(Prompt(template="{input}"), _benchmark())
    payload = run.model_dump(mode="json")
    payload["gabarito_hash"] = payload.pop("benchmark_hash")
    payload["config"]["use_gabarito_split"] = payload["config"].pop("use_benchmark_split")
    payload["task_contract"]["invariants"] = [
        {"text": "Preserve the expected labels.", "source": "gabarito"}
    ]
    legacy = json.dumps(payload)
    files = FileRunStore(tmp_path / "legacy")
    directory = files.root / run.id
    directory.mkdir()
    path = directory / "run.json"
    path.write_text(legacy)
    sqlite = SQLiteRunStore(tmp_path / "legacy.sqlite")
    await sqlite.save_run(run)
    with closing(sqlite3.connect(sqlite.path)) as connection, connection:
        connection.execute("UPDATE runs SET payload = ? WHERE id = ?", (legacy, run.id))
    for store in (files, sqlite):
        loaded = await store.load_run(run.id)
        assert loaded.benchmark_hash == run.benchmark_hash
        assert loaded.gabarito_hash == run.benchmark_hash
        assert loaded.best_iteration.score == 100
        assert loaded.task_contract.invariants[0].source == "benchmark"
        assert OptimizationRun.model_validate_json(loaded.model_dump_json()).id == run.id
    assert path.read_text() == legacy
    with closing(sqlite3.connect(sqlite.path)) as connection, connection:
        assert (
            connection.execute("SELECT payload FROM runs WHERE id = ?", (run.id,)).fetchone()[0]
            == legacy
        )


@pytest.mark.parametrize("legacy", [False, True])
def test_rest_requests_accept_current_and_legacy_benchmark_fields(tmp_path, legacy):
    client = TestClient(create_api_app(SQLiteRunStore(tmp_path / "api.sqlite")))
    response = client.post(
        "/runs",
        json={
            "prompt": {"template": "{input}", "variables": ["input"]},
            "gabarito" if legacy else "benchmark": _benchmark().model_dump(mode="json"),
            "config": _config().model_dump(mode="json"),
            "mode": "validate",
        },
    )
    assert response.status_code == 200
    task = client.get(f"/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "completed"
    run = client.get(f"/runs/{task['run_id']}").json()
    assert run["iterations"][0]["score_report"]["global_score"] == 100
    assert run["gabarito_hash"] == run["benchmark_hash"]
    assert run["config"]["use_gabarito_split"] is False


def test_dashboard_accepts_legacy_form_fields(tmp_path):
    client = TestClient(create_dashboard_app(SQLiteRunStore(tmp_path / "web.sqlite")))
    response = client.post(
        "/runs/new",
        data={
            "mode": "validate",
            "prompt_content": "{input}",
            "gabarito_content": yaml.safe_dump(_benchmark().model_dump(mode="json")),
            "config_content": yaml.safe_dump(_config().model_dump(mode="json")),
        },
    )
    assert response.status_code == 200
    assert "completed" in response.text


def _write_project(directory: Path):
    (directory / "prompt.txt").write_text("{input}")
    (directory / "gabarito.yaml").write_text(yaml.safe_dump(_benchmark(8).model_dump(mode="json")))
    (directory / "config.yaml").write_text(yaml.safe_dump(_config().model_dump(mode="json")))


@pytest.mark.parametrize("option", ["--gabarito", "-g", "--benchmark", "-b"])
def test_cli_accepts_both_benchmark_option_names(tmp_path, option):
    _write_project(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "validate",
            "--prompt",
            str(tmp_path / "prompt.txt"),
            option,
            str(tmp_path / "gabarito.yaml"),
            "--config",
            str(tmp_path / "config.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "100.00" in result.output


def test_cli_uses_legacy_default_filename_and_split_command(tmp_path):
    _write_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["optimize", "--config", str(tmp_path / "config.yaml")])
    assert result.exit_code == 0, result.output
    assert "score=100.00" in result.output
    result = runner.invoke(
        app,
        [
            "split-gabarito",
            "--gabarito",
            str(tmp_path / "gabarito.yaml"),
            "--output-dir",
            str(tmp_path / "splits"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "splits/gabarito.train.yaml").exists()
    assert sum(len(Gabarito.from_yaml(p).cases) for p in (tmp_path / "splits").glob("*.yaml")) == 8


@pytest.mark.parametrize(
    ("current", "preserved", "removed"),
    [
        (
            "Classify future events only. Do not invent information. {input}",
            "Use only information present in the input to classify future events. {input}",
            "Classify all events and invent missing information. {input}",
        ),
        (
            "Classifique apenas eventos futuros. Não invente informação. {input}",
            "Use apenas informações presentes no input para classificar eventos futuros. {input}",
            "Classifique todos os eventos e invente dados ausentes. {input}",
        ),
    ],
)
def test_task_constraints_are_preserved_for_english_and_existing_portuguese_tasks(
    current, preserved, removed
):
    prompt = Prompt(template=current, variables=["input"])
    contract = build_task_contract(prompt, _benchmark(), _config())
    assert contract.negative_rules
    assert contract.invariants
    assert not validate_refinement_against_contract(_proposal(preserved), prompt, contract)
    violations = validate_refinement_against_contract(_proposal(removed), prompt, contract)
    assert "future-events restriction was removed" in violations
    assert "rule against inventing information was removed" in violations


def test_legacy_saved_contract_rules_are_still_enforced():
    prompt = Prompt(template="{input}", variables=["input"])
    contract = build_task_contract(prompt, _benchmark(), _config())
    contract.negative_rules = [ContractRule(text="Não inventar informação.", source="prompt")]
    contract.invariants = [
        ContractRule(text="Classificar apenas eventos futuros.", source="prompt")
    ]
    violations = validate_refinement_against_contract(
        _proposal("Answer freely. {input}"), prompt, contract
    )
    assert "future-events restriction was removed" in violations
    assert "rule against inventing information was removed" in violations


def test_cli_new_default_path_opens_existing_legacy_project(tmp_path):
    _write_project(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "validate",
            "--prompt",
            str(tmp_path / "prompt.txt"),
            "--benchmark",
            str(tmp_path / "benchmark.yaml"),
            "--config",
            str(tmp_path / "config.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "100.00" in result.output
    assert not (tmp_path / "benchmark.yaml").exists()


def test_import_command_keeps_legacy_alias(tmp_path):
    source = tmp_path / "examples.jsonl"
    source.write_text('{"input":"ok","expected_output":"ok"}\n')
    output = tmp_path / "imported.yaml"
    result = CliRunner().invoke(
        app,
        ["import-gabarito", "--source", "jsonl", "--input", str(source), "--output", str(output)],
    )
    assert result.exit_code == 0, result.output
    assert Gabarito.from_yaml(output).cases[0].expected_output == "ok"


@pytest.mark.asyncio
async def test_portuguese_task_rejects_drift_and_repairs_before_next_execution():
    from crucible.modules.optimizer.adapters.providers.fake import FakeProvider

    benchmark = Benchmark.model_validate(
        {
            "name": "existing-task",
            "version": "v1",
            "cases": [
                {
                    "id": "deadline",
                    "input": "Intime-se no prazo de 5 dias.",
                    "expected_output": (
                        '{"classification":"Prazo","text_validation":"prazo de 5 dias"}'
                    ),
                    "assertion": {"type": "field_by_field"},
                }
            ],
        }
    )
    current = Prompt(
        template="Extraia o trecho literal em text_validation. Não invente informação. {input}",
        variables=["input"],
    )
    responses = iter(
        [
            {
                "pattern": "inferred evidence",
                "hypothesis": "extract the passage",
                "category": "LITERAL_EXTRACTION",
                "confidence": 0.9,
            },
            {
                "new_prompt": "Explique por que em text_validation. {input}",
                "diff_summary": "drift",
                "rationale": "inference",
                "confidence": 0.9,
            },
            {
                "new_prompt": (
                    "Classifique em classification. Extraia o trecho exato em text_validation. "
                    "Não invente informação. {input}"
                ),
                "diff_summary": "repair",
                "rationale": "literal extraction",
                "confidence": 0.9,
            },
        ]
    )
    reasoning = FakeProvider(lambda _: json.dumps(next(responses)))
    target = FakeProvider(
        lambda p: (
            '{"classification":"Prazo","text_validation":"prazo de 5 dias"}'
            if p.startswith("Classifique")
            else '{"classification":"Prazo","text_validation":"Existe prazo."}'
        )
    )
    run = await Optimizer(_config(), target_provider=target, reasoning_provider=reasoning).optimize(
        current, gabarito=benchmark
    )
    assert run.stop_reason == "threshold_reached"
    assert len(target.prompts) == 2
    assert len(run.iterations[0].refinement_repair_attempts) == 1
    assert run.best_iteration.score == 100
    assert run.best_iteration.prompt.template.startswith("Classifique")
    assert "Preserve the task language" in reasoning.prompts[-1]


@pytest.mark.asyncio
async def test_legacy_model_comparison_keyword():
    from crucible import ComparisonTarget

    config = OptimizationConfig(
        comparison_models=[
            ComparisonTarget(
                label="echo", model=ModelSpec(provider="fake", model_id="echo", role="target")
            )
        ]
    )
    run = await Optimizer(config).compare_models(Prompt(template="{input}"), gabarito=_benchmark())
    assert run.stop_reason == "comparison_completed"
    assert run.comparison_summary.best_score.label == "echo"
    assert run.best_iteration.score == 100
