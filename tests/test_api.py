from fastapi.testclient import TestClient

from crucible import ComparisonTarget, Contains, Gabarito, ModelSpec, OptimizationConfig, Prompt
from crucible import TestCase as CrucibleTestCase
from crucible.modules.optimizer.adapters.storage import SQLiteRunStore
from crucible.modules.optimizer.presentation.api.app import create_api_app


def test_api_lists_and_reads_runs(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    client = TestClient(create_api_app(store))
    request = {
        "prompt": Prompt(template="{input}", variables=["input"]).model_dump(mode="json"),
        "gabarito": Gabarito(
            name="sample",
            version="v1",
            cases=[
                CrucibleTestCase(
                    id="case",
                    input="ok",
                    expected_output="ok",
                    assertion=Contains(),
                )
            ],
        ).model_dump(mode="json"),
        "config": OptimizationConfig(
            threshold=100,
            max_iterations=1,
            target_model=ModelSpec(provider="fake", model_id="target", role="target"),
            reasoning_model=ModelSpec(provider="fake", model_id="reasoning", role="reasoning"),
        ).model_dump(mode="json"),
    }

    created = client.post("/runs", json=request)

    assert created.status_code == 200
    task_id = created.json()["task_id"]
    task = client.get(f"/tasks/{task_id}").json()
    assert task["status"] == "completed"
    run_id = task["run_id"]
    assert client.get("/runs").json()[0]["id"] == run_id
    assert client.get(f"/runs/{run_id}").json()["id"] == run_id
    report = client.post(f"/runs/{run_id}/reports/html")
    assert report.status_code == 200


def test_api_can_create_validate_run(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    client = TestClient(create_api_app(store))
    request = {
        "mode": "validate",
        "prompt": Prompt(template="{input}", variables=["input"]).model_dump(mode="json"),
        "gabarito": Gabarito(
            name="sample",
            version="v1",
            cases=[
                CrucibleTestCase(
                    id="case",
                    input="ok",
                    expected_output="ok",
                    assertion=Contains(),
                )
            ],
        ).model_dump(mode="json"),
        "config": OptimizationConfig(
            threshold=100,
            max_iterations=1,
            target_model=ModelSpec(provider="fake", model_id="target", role="target"),
            reasoning_model=ModelSpec(provider="fake", model_id="reasoning", role="reasoning"),
        ).model_dump(mode="json"),
    }

    created = client.post("/runs", json=request)

    assert created.status_code == 200
    task = client.get(f"/tasks/{created.json()['task_id']}").json()
    assert task["status"] == "completed"
    run = client.get(f"/runs/{task['run_id']}").json()
    assert run["run_mode"] == "validate"
    assert run["stop_reason"] == "validation_only"
    assert len(run["iterations"]) == 1


def test_api_can_create_compare_run(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    client = TestClient(create_api_app(store))
    config = OptimizationConfig(
        threshold=100,
        max_iterations=1,
        comparison_models=[
            ComparisonTarget(
                label="fake-a",
                model=ModelSpec(provider="fake", model_id="target-a", role="target"),
            ),
            ComparisonTarget(
                label="fake-b",
                model=ModelSpec(provider="fake", model_id="target-b", role="target"),
            ),
        ],
    )
    request = {
        "mode": "compare",
        "prompt": Prompt(template="{input}", variables=["input"]).model_dump(mode="json"),
        "gabarito": Gabarito(
            name="sample",
            version="v1",
            cases=[
                CrucibleTestCase(
                    id="case",
                    input="ok",
                    expected_output="ok",
                    assertion=Contains(),
                )
            ],
        ).model_dump(mode="json"),
        "config": config.model_dump(mode="json", by_alias=True),
    }

    created = client.post("/runs", json=request)

    assert created.status_code == 200
    task = client.get(f"/tasks/{created.json()['task_id']}").json()
    assert task["status"] == "completed"
    run = client.get(f"/runs/{task['run_id']}").json()
    assert run["run_mode"] == "compare"
    assert run["stop_reason"] == "comparison_completed"
    assert len(run["iterations"]) == 2
    assert [iteration["comparison_label"] for iteration in run["iterations"]] == [
        "fake-a",
        "fake-b",
    ]
    assert run["comparison_summary"]["best_score"]["label"] in {"fake-a", "fake-b"}
    assert run["comparison_summary"]["best_score"]["score"] == 100.0


def test_api_persists_task_state_and_accepts_cancel(tmp_path):
    db = tmp_path / "runs.sqlite"
    store = SQLiteRunStore(db)
    store.create_task("task-1")

    client = TestClient(create_api_app(SQLiteRunStore(db)))

    cancel = client.post("/tasks/task-1/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["cancel_requested"] is True

    loaded = client.get("/tasks/task-1")
    assert loaded.status_code == 200
    assert loaded.json()["status"] == "cancel_requested"
