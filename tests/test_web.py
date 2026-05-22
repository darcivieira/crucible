import asyncio

from fastapi.testclient import TestClient

from crucible import Contains, ModelSpec, OptimizationConfig, Prompt
from crucible import TestCase as CrucibleTestCase
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.domain.models import (
    ExecutionResult,
    Iteration,
    OptimizationRun,
    Verdict,
)
from crucible.modules.optimizer.domain.scoring import aggregate_score
from crucible.modules.optimizer.presentation.web.app import create_dashboard_app


def test_dashboard_routes(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_run(store)
    client = TestClient(create_dashboard_app(store))

    index_response = client.get("/")
    detail_response = client.get(f"/runs/{run.id}")
    diff_response = client.get(f"/runs/{run.id}/diff")
    verdicts_response = client.get(f"/runs/{run.id}/iterations/1/verdicts")
    regressions_response = client.get(f"/runs/{run.id}/regressions")
    compare_response = client.get(f"/compare?left={run.id}&right={run.id}")
    api_runs_response = client.get("/api/runs")
    api_run_response = client.get(f"/api/runs/{run.id}")

    assert index_response.status_code == 200
    assert run.id in index_response.text
    assert detail_response.status_code == 200
    assert "Best prompt" in detail_response.text
    assert diff_response.status_code == 200
    assert "+novo {input}" in diff_response.text
    assert verdicts_response.status_code == 200
    assert "Verdicts 1" in verdicts_response.text
    assert regressions_response.status_code == 200
    assert compare_response.status_code == 200
    assert "Compare Runs" in compare_response.text
    assert api_runs_response.status_code == 200
    assert api_runs_response.json()[0]["id"] == run.id
    assert api_run_response.status_code == 200
    assert api_run_response.json()["id"] == run.id


def test_dashboard_returns_404_for_missing_run(tmp_path):
    client = TestClient(create_dashboard_app(SQLiteRunStore(tmp_path / "runs.sqlite")))

    response = client.get("/runs/missing")

    assert response.status_code == 404


def _saved_run(store: SQLiteRunStore) -> OptimizationRun:
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
    asyncio.run(store.save_run(run))
    return run
