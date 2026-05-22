import json

import pytest

from crucible import (
    Contains,
    Gabarito,
    ModelParams,
    ModelSpec,
    OptimizationConfig,
    Optimizer,
    Prompt,
)
from crucible import (
    TestCase as CrucibleTestCase,
)
from crucible.modules.optimizer.adapters.providers.fake import FakeProvider


class MemoryStore:
    def __init__(self):
        self.runs = []

    async def save_run(self, run):
        self.runs.append(run)

    async def save_iteration(self, run):
        self.runs.append(run)

    async def load_run(self, run_id):
        return self.runs[-1]


class MemoryCache:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value


def _config(max_iterations=3, threshold=100):
    return OptimizationConfig(
        threshold=threshold,
        max_iterations=max_iterations,
        target_model=ModelSpec(provider="fake", model_id="target", role="target"),
        reasoning_model=ModelSpec(
            provider="fake",
            model_id="reasoning",
            role="reasoning",
            params=ModelParams(max_tokens=256),
        ),
    )


def _gabarito():
    return Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id="case-1",
                input="Retorne ok",
                expected_output="ok",
                assertion=Contains(),
                tags=["smoke"],
            )
        ],
    )


@pytest.mark.asyncio
async def test_validate_executes_cases_and_scores():
    optimizer = Optimizer(
        _config(),
        target_provider=FakeProvider(lambda prompt: "ok"),
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    iteration = await optimizer.validate(
        Prompt(template="{input}", variables=["input"]), _gabarito()
    )

    assert iteration.score == 100
    assert iteration.verdicts[0].passed is True


@pytest.mark.asyncio
async def test_optimize_returns_best_seen_prompt_after_refinement():
    calls = {"target": 0, "reasoning": 0}

    def target_response(prompt):
        calls["target"] += 1
        return "wrong" if calls["target"] == 1 else "ok"

    def reasoning_response(prompt):
        calls["reasoning"] += 1
        if calls["reasoning"] == 1:
            return json.dumps(
                {
                    "pattern": "missing exact instruction",
                    "hypothesis": "prompt is vague",
                    "category": "INSTRUCTION_AMBIGUITY",
                    "confidence": 0.8,
                    "is_model_limitation": False,
                }
            )
        return json.dumps(
            {
                "new_prompt": "Responda exatamente ok para: {input}",
                "diff_summary": "adds exact output",
                "rationale": "forces expected answer",
                "expected_improvement": "higher precision",
                "confidence": 0.9,
            }
        )

    optimizer = Optimizer(
        _config(max_iterations=3, threshold=100),
        target_provider=FakeProvider(target_response),
        reasoning_provider=FakeProvider(reasoning_response),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(Prompt(template="{input}", variables=["input"]), _gabarito())

    assert run.stop_reason == "threshold_reached"
    assert run.best_iteration is not None
    assert run.best_iteration.score == 100
    assert run.best_iteration.version == 1


@pytest.mark.asyncio
async def test_optimize_stops_at_max_iterations():
    optimizer = Optimizer(
        _config(max_iterations=1, threshold=100),
        target_provider=FakeProvider(lambda prompt: "wrong"),
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(Prompt(template="{input}", variables=["input"]), _gabarito())

    assert run.stop_reason == "max_iterations"
    assert len(run.iterations) == 1


@pytest.mark.asyncio
async def test_validate_supports_multiple_runs_per_case():
    responses = iter(["wrong", "ok", "ok"])
    config = _config()
    config.n_runs_per_case = 3
    optimizer = Optimizer(
        config,
        target_provider=FakeProvider(lambda prompt: next(responses)),
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    iteration = await optimizer.validate(
        Prompt(template="{input}", variables=["input"]), _gabarito()
    )

    assert iteration.score == 100
    assert iteration.verdicts[0].execution.actual_output == "ok"
    assert iteration.verdicts[0].assertion_detail["runs"]["majority_count"] == 2
    assert iteration.verdicts[0].assertion_detail["runs"]["unstable"] is True


@pytest.mark.asyncio
async def test_optimize_with_gabarito_split_records_validation_scores():
    config = _config(max_iterations=1, threshold=100)
    config.use_gabarito_split = True
    gabarito = Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id=f"case-{index}",
                input="Retorne ok",
                expected_output="ok",
                assertion=Contains(),
            )
            for index in range(3)
        ],
    )
    optimizer = Optimizer(
        config,
        target_provider=FakeProvider(lambda prompt: "ok"),
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(Prompt(template="{input}", variables=["input"]), gabarito)

    assert run.validation_scores["train"] == 100
    assert run.validation_scores["val"] == 100
    assert run.validation_scores["test"] == 100


@pytest.mark.asyncio
async def test_optimizer_records_multi_objective_and_active_learning():
    config = _config(max_iterations=1, threshold=100)
    config.selection_strategy = "multi_objective"
    config.objective_quality_weight = 1.0
    config.objective_cost_weight = 0.2
    config.active_learning_suggestions = 1
    optimizer = Optimizer(
        config,
        target_provider=FakeProvider(lambda prompt: "wrong"),
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(Prompt(template="{input}", variables=["input"]), _gabarito())

    assert run.iterations[0].objective_score is not None
    assert run.pareto_frontier_versions == [0]
    assert run.active_learning_suggestions[0].test_case_id == "case-1"


@pytest.mark.asyncio
async def test_optimizer_honors_cancellation_before_iteration():
    optimizer = Optimizer(
        _config(max_iterations=1, threshold=100),
        target_provider=FakeProvider(lambda prompt: "ok"),
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
        should_cancel=lambda: True,
    )

    run = await optimizer.optimize(Prompt(template="{input}", variables=["input"]), _gabarito())

    assert run.status == "aborted"
    assert run.stop_reason == "cancelled"
    assert run.iterations == []
