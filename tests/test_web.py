import asyncio

from fastapi.testclient import TestClient

from crucible import Contains, ModelSpec, OptimizationConfig, Prompt
from crucible import TestCase as CrucibleTestCase
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.domain.models import (
    ComparisonCaseWinner,
    ComparisonSummary,
    ComparisonWinner,
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
    assert "Download PDF" in detail_response.text
    assert diff_response.status_code == 200
    assert "+novo {input}" in diff_response.text
    assert verdicts_response.status_code == 200
    assert "Verdicts 1" in verdicts_response.text
    assert "Prompt used" in verdicts_response.text
    assert "novo {input}" in verdicts_response.text
    assert regressions_response.status_code == 200
    assert compare_response.status_code == 200
    assert "Compare runs" in compare_response.text
    assert api_runs_response.status_code == 200
    assert api_runs_response.json()[0]["id"] == run.id
    assert api_run_response.status_code == 200
    assert api_run_response.json()["id"] == run.id


def test_dashboard_shows_comparison_summary(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_comparison_run(store)
    client = TestClient(create_dashboard_app(store))

    response = client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert "Model comparison" in response.text
    assert "Best value" in response.text
    assert "case" in response.text


def test_dashboard_downloads_pdf_report(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_run(store)
    client = TestClient(create_dashboard_app(store))

    response = client.get(f"/runs/{run.id}/reports/pdf/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert f"crucible-{run.id}.pdf" in response.headers["content-disposition"]


def test_dashboard_blocks_pdf_download_for_unfinished_run(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_run(store, status="running")
    client = TestClient(create_dashboard_app(store))

    detail = client.get(f"/runs/{run.id}")
    response = client.get(f"/runs/{run.id}/reports/pdf/download")

    assert detail.status_code == 200
    assert "Download PDF" not in detail.text
    assert response.status_code == 409
    assert response.json()["detail"] == "Run has not finished yet"


def test_dashboard_new_run_form_creates_validate_task(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    client = TestClient(create_dashboard_app(store))

    response = client.post(
        "/runs/new",
        data={
            "mode": "validate",
            "prompt_content": "{input}",
            "benchmark_content": """
name: sample
version: v1
cases:
  - id: case
    input: ok
    expected_output: ok
    assertion:
      type: contains
""",
            "config_content": """
threshold: 100
max_iterations: 1
target_model:
  provider: fake
  model_id: target
  role: target
reasoning_model:
  provider: fake
  model_id: reasoning
  role: reasoning
""",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    task_response = client.get(response.headers["location"])
    assert task_response.status_code == 200
    assert "completed" in task_response.text
    run_id = store.list_runs()[0].id
    run = asyncio.run(store.load_run(run_id))
    assert run.run_mode == "validate"
    assert run.stop_reason == "validation_only"


def test_dashboard_new_run_form_shows_validation_errors(tmp_path):
    client = TestClient(create_dashboard_app(SQLiteRunStore(tmp_path / "runs.sqlite")))

    response = client.post(
        "/runs/new",
        data={
            "mode": "optimize",
            "prompt_content": "{input}",
            "benchmark_content": "not: a valid benchmark",
            "config_content": "not: a valid config",
        },
    )

    assert response.status_code == 422
    assert "Could not create the run" in response.text


def test_dashboard_new_run_form_creates_compare_task(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    client = TestClient(create_dashboard_app(store))

    response = client.post(
        "/runs/new",
        data={
            "mode": "compare",
            "prompt_content": "{input}",
            "benchmark_content": """
name: sample
version: v1
cases:
  - id: case
    input: ok
    expected_output: ok
    assertion:
      type: contains
""",
            "config_content": """
threshold: 100
max_iterations: 1
comparison_models:
  - label: fake-a
    model:
      provider: fake
      model_id: target-a
      role: target
  - label: fake-b
    model:
      provider: fake
      model_id: target-b
      role: target
""",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    run_id = store.list_runs()[0].id
    run = asyncio.run(store.load_run(run_id))
    assert run.run_mode == "compare"
    assert run.stop_reason == "comparison_completed"


def test_dashboard_filters_verdicts(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_run(store)
    client = TestClient(create_dashboard_app(store))

    response = client.get(f"/runs/{run.id}/iterations/1/verdicts?passed=false")

    assert response.status_code == 200
    assert "No verdicts found" in response.text


def test_dashboard_returns_404_for_missing_run(tmp_path):
    client = TestClient(create_dashboard_app(SQLiteRunStore(tmp_path / "runs.sqlite")))

    response = client.get("/runs/missing")

    assert response.status_code == 404


def _saved_run(store: SQLiteRunStore, status: str = "completed") -> OptimizationRun:
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
    run = OptimizationRun(config=config, benchmark_hash="g", initial_prompt_hash="p")
    run.status = status
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


def _saved_comparison_run(store: SQLiteRunStore) -> OptimizationRun:
    case = CrucibleTestCase(id="case", input="ok", expected_output="ok", assertion=Contains())
    config = OptimizationConfig(
        target_model=ModelSpec(provider="fake", model_id="t", role="target"),
        reasoning_model=ModelSpec(provider="fake", model_id="r", role="reasoning"),
    )
    run = OptimizationRun(
        run_mode="compare",
        config=config,
        benchmark_hash="g",
        initial_prompt_hash="p",
        status="completed",
        stop_reason="comparison_completed",
        comparison_summary=ComparisonSummary(
            best_score=ComparisonWinner(label="accurate", score=100, cost_usd=0.02),
            lowest_cost=ComparisonWinner(label="cheap", score=70, cost_usd=0.01),
            best_value=ComparisonWinner(label="accurate", score=100, cost_usd=0.02),
            case_winners=[
                ComparisonCaseWinner(
                    test_case_id="case",
                    best_score="accurate",
                    lowest_cost="cheap",
                    best_value="accurate",
                )
            ],
        ),
    )
    first_verdict = Verdict(
        test_case=case,
        execution=ExecutionResult(test_case_id="case", actual_output="wrong", latency_ms=4),
        score=0.7,
        passed=False,
    )
    second_verdict = Verdict(
        test_case=case,
        execution=ExecutionResult(
            test_case_id="case",
            actual_output="ok",
            latency_ms=8,
            cost_usd=0.02,
        ),
        score=1,
        passed=True,
    )
    run.iterations.extend(
        [
            Iteration(
                version=0,
                prompt=Prompt(template="{input}", variables=["input"]),
                verdicts=[first_verdict],
                score_report=aggregate_score([first_verdict]),
                comparison_label="cheap",
            ),
            Iteration(
                version=1,
                prompt=Prompt(template="{input}", variables=["input"]),
                verdicts=[second_verdict],
                score_report=aggregate_score([second_verdict]),
                comparison_label="accurate",
            ),
        ]
    )
    asyncio.run(store.save_run(run))
    return run


def test_dashboard_mode_filter_combines_with_existing_filters(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    optimized = _saved_run(store)
    compared = _saved_comparison_run(store)
    client = TestClient(create_dashboard_app(store))

    response = client.get("/?mode=compare&status=completed&min_score=90")

    assert response.status_code == 200
    assert compared.id in response.text
    assert optimized.id not in response.text
    assert 'name="mode" value="compare"' in response.text
    assert 'aria-current="page">Model comparisons' in response.text


def test_scorecard_uses_actual_values_and_correct_improvement_direction(tmp_path):
    from crucible.modules.optimizer.presentation.web.app import _scorecard

    run = _saved_run(SQLiteRunStore(tmp_path / "runs.sqlite"))
    run.iterations[0].score_report.operational.total_cost_usd = 0.02
    run.iterations[1].score_report.operational.total_cost_usd = 0.01
    run.iterations[0].score_report.operational.p95_latency_ms = 40
    run.iterations[1].score_report.operational.p95_latency_ms = 80

    score, passed, cost, latency = _scorecard(run)

    assert score["delta"] == 100
    assert score["tone"] == passed["tone"] == "good"
    assert cost["delta_text"] == "−$0.0100"
    assert cost["tone"] == "good"
    assert cost["direction"] == "negative"
    assert latency["delta_text"] == "+40 ms"
    assert latency["tone"] == "bad"
    assert all(0 <= row["width"] <= 44 for row in (score, passed, cost, latency))


def test_scorecard_handles_zero_values_and_empty_runs(tmp_path):
    from crucible.modules.optimizer.presentation.web.app import _scorecard

    run = _saved_run(SQLiteRunStore(tmp_path / "runs.sqlite"))
    assert _scorecard(run)[2]["tone"] == "neutral"
    assert _scorecard(run)[2]["width"] == 0
    empty = run.model_copy(update={"iterations": []})
    assert _scorecard(empty) == []
    assert _scorecard(run, empty) == []


def test_regression_filters_apply_to_the_scoped_case_list(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_run(store)
    run.iterations[1].verdicts[0].is_regression = True
    asyncio.run(store.save_run(run))
    client = TestClient(create_dashboard_app(store))

    present = client.get(f"/runs/{run.id}/regressions?case_id=case")
    filtered = client.get(f"/runs/{run.id}/regressions?case_id=missing")

    assert present.status_code == filtered.status_code == 200
    assert "No verdicts found" not in present.text
    assert "No verdicts found" in filtered.text


def test_dashboard_static_assets_and_form_labels(tmp_path):
    client = TestClient(create_dashboard_app(SQLiteRunStore(tmp_path / "runs.sqlite")))
    response = client.get("/runs/new")
    assert 'for="prompt-content"' in response.text
    assert 'id="prompt-content"' in response.text
    for name, media in [
        ("dashboard.css", "text/css"),
        ("dashboard.js", "javascript"),
        ("favicon.svg", "image/svg+xml"),
    ]:
        asset = client.get(f"/static/{name}")
        assert asset.status_code == 200
        assert media in asset.headers["content-type"]


def test_browser_filters_accept_empty_optional_numeric_inputs(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    run = _saved_run(store)
    client = TestClient(create_dashboard_app(store))

    assert client.get("/?target=fake&status=&min_score=").status_code == 200
    response = client.get(
        f"/runs/{run.id}/iterations/1/verdicts?case_id=case&passed=&min_score=&max_score="
    )
    assert response.status_code == 200
    assert "No verdicts found" not in response.text
    assert client.get(f"/runs/{run.id}/regressions?min_score=&max_score=").status_code == 200
    assert client.get("/?min_score=invalid").status_code == 422
