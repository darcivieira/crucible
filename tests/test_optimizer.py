import json

import pytest

from crucible import (
    ComparisonTarget,
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
from crucible.modules.optimizer.application.contracts import (
    build_task_contract,
    validate_refinement_against_contract,
)
from crucible.modules.optimizer.domain.assertions import FieldByField
from crucible.modules.optimizer.domain.models import (
    CompletionResult,
    ModelOutputFormat,
    RefinementProposal,
)


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


class SequencedProvider:
    def __init__(self, results):
        self.results = list(results)
        self.prompts = []

    async def complete(self, prompt, params):
        self.prompts.append(prompt)
        return self.results.pop(0)


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
async def test_validate_requires_target_and_reasoning_models():
    config = _config()
    config.target_model = None

    optimizer = Optimizer(config, store=MemoryStore(), cache=MemoryCache())

    with pytest.raises(ValueError, match="target_model is required for validate"):
        await optimizer.validate(Prompt(template="{input}", variables=["input"]), _gabarito())


@pytest.mark.asyncio
async def test_optimize_requires_reasoning_model():
    config = _config()
    config.reasoning_model = None

    optimizer = Optimizer(config, store=MemoryStore(), cache=MemoryCache())

    with pytest.raises(ValueError, match="reasoning_model is required for optimize"):
        await optimizer.optimize(Prompt(template="{input}", variables=["input"]), _gabarito())


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
async def test_optimize_normalizes_reasoning_confidence_scales():
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
                    "confidence": 5.0,
                    "is_model_limitation": False,
                }
            )
        return json.dumps(
            {
                "new_prompt": "Responda exatamente ok para: {input}",
                "diff_summary": "adds exact output",
                "rationale": "forces expected answer",
                "expected_improvement": "higher precision",
                "confidence": 80,
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

    assert run.iterations[1].diagnosis is not None
    assert run.iterations[1].diagnosis.confidence == 0.5
    assert run.iterations[1].refinement_rationale == "forces expected answer"


def test_task_contract_detects_literal_extraction_from_prompt_and_gabarito():
    config = _config()
    config.target_model.output_format = ModelOutputFormat(
        type="json_schema",
        schema={
            "type": "object",
            "required": ["classification", "text_validation"],
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["Nenhum", "Prazo"],
                },
                "text_validation": {"type": "string"},
            },
        },
    )
    gabarito = Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id="case-1",
                input="Intime-se no prazo de 5 dias.",
                expected_output=(
                    '{"classification": "Prazo", '
                    '"text_validation": "Intime-se no prazo de 5 dias."}'
                ),
                assertion=FieldByField(weights={"classification": 95, "text_validation": 5}),
            )
        ],
    )

    contract = build_task_contract(
        Prompt(
            template="Classifique e extraia o trecho exato que justifica a classe.\n{input}",
            variables=["input"],
        ),
        gabarito,
        config,
    )

    assert "text_validation" in contract.literal_extraction_fields
    assert contract.output_contract["fields"] == ["classification", "text_validation"]
    assert any("extração literal" in rule.text for rule in contract.invariants)


def test_contract_accepts_equivalent_no_invention_wording():
    config = _config()
    gabarito = _gabarito()
    current = Prompt(
        template="Não invente informação.\n{input}",
        variables=["input"],
    )
    contract = build_task_contract(current, gabarito, config)
    proposal = RefinementProposal(
        new_prompt="Responda com base apenas nas informações presentes no input.\n{input}",
        diff_summary="preserves no invention",
        rationale="keeps source-bound behavior",
        confidence=0.8,
    )

    violations = validate_refinement_against_contract(proposal, current, contract)

    assert "regra de não inventar informação foi removida" not in violations


@pytest.mark.asyncio
async def test_optimizer_rejects_refinement_that_turns_literal_extraction_into_inference():
    calls = {"reasoning": 0}
    config = _config(max_iterations=2, threshold=100)
    config.max_refinement_repair_attempts = 2
    config.target_model.output_format = ModelOutputFormat(
        type="json_schema",
        schema={
            "type": "object",
            "required": ["classification", "text_validation"],
            "properties": {
                "classification": {
                    "type": "string",
                    "enum": ["Nenhum", "Prazo"],
                },
                "text_validation": {"type": "string"},
            },
        },
    )
    gabarito = Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id="case-1",
                input="Intime-se no prazo de 5 dias.",
                expected_output=(
                    '{"classification": "Prazo", '
                    '"text_validation": "Intime-se no prazo de 5 dias."}'
                ),
                assertion=FieldByField(weights={"classification": 95, "text_validation": 5}),
            )
        ],
    )

    def reasoning_response(prompt):
        calls["reasoning"] += 1
        if calls["reasoning"] == 1:
            assert "CONTRATO DA TAREFA" in prompt
            return json.dumps(
                {
                    "pattern": "text_validation is inferred",
                    "hypothesis": "prompt needs stronger evidence extraction",
                    "category": "LITERAL_EXTRACTION",
                    "confidence": 0.9,
                    "is_model_limitation": False,
                }
            )
        assert (
            "CASOS FALHOS QUE MOTIVAM O REFINO" in prompt
            or "VIOLAÇÕES QUE DEVEM SER CORRIGIDAS" in prompt
        )
        return json.dumps(
            {
                "new_prompt": (
                    "Classifique em classification e explique por que em text_validation. {input}"
                ),
                "diff_summary": "turns evidence into rationale",
                "rationale": "asks for explanation",
                "expected_improvement": "more descriptive output",
                "preserved_invariants": [],
                "changed_behavior": ["text_validation becomes rationale"],
                "risk_of_regression": "high",
                "confidence": 0.8,
            }
        )

    initial = Prompt(
        template=(
            "Classifique a publicação e extraia o trecho exato em text_validation. "
            "Não invente informação.\n{input}"
        ),
        variables=["input"],
    )
    optimizer = Optimizer(
        config,
        target_provider=FakeProvider(
            lambda prompt: (
                '{"classification": "Prazo", "text_validation": "O texto contém prazo."}'
            )
        ),
        reasoning_provider=FakeProvider(reasoning_response),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(initial, gabarito)

    assert run.stop_reason == "reasoning_failed_to_refine"
    assert run.task_contract is not None
    assert run.iterations[0].refinement_rejected_reason is not None
    assert len(run.iterations[0].refinement_repair_attempts) == 2
    assert "explicação/inferência" in run.iterations[0].refinement_rejected_reason
    assert len(run.iterations) == 1


@pytest.mark.asyncio
async def test_optimizer_repairs_invalid_refinement_before_next_target_iteration():
    calls = {"target": 0, "reasoning": 0}
    config = _config(max_iterations=3, threshold=100)
    config.max_refinement_repair_attempts = 3
    config.target_model.output_format = ModelOutputFormat(
        type="json_schema",
        schema={
            "type": "object",
            "required": ["classification", "text_validation"],
            "properties": {
                "classification": {"type": "string", "enum": ["Nenhum", "Prazo"]},
                "text_validation": {"type": "string"},
            },
        },
    )
    gabarito = Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id="case-1",
                input="Intime-se no prazo de 5 dias.",
                expected_output=(
                    '{"classification": "Prazo", '
                    '"text_validation": "Intime-se no prazo de 5 dias."}'
                ),
                assertion=FieldByField(weights={"classification": 95, "text_validation": 5}),
            )
        ],
    )

    def target_response(prompt):
        calls["target"] += 1
        if calls["target"] == 1:
            return '{"classification": "Prazo", "text_validation": "O texto contém prazo."}'
        return (
            '{"classification": "Prazo", '
            '"text_validation": "Intime-se no prazo de 5 dias."}'
        )

    def reasoning_response(prompt):
        calls["reasoning"] += 1
        if calls["reasoning"] == 1:
            return json.dumps(
                {
                    "pattern": "text_validation is inferred",
                    "hypothesis": "prompt needs literal extraction",
                    "category": "LITERAL_EXTRACTION",
                    "confidence": 0.9,
                    "is_model_limitation": False,
                }
            )
        if calls["reasoning"] == 2:
            return json.dumps(
                {
                    "new_prompt": (
                        "Classifique em classification e explique por que em text_validation. "
                        "{input}"
                    ),
                    "diff_summary": "turns evidence into rationale",
                    "rationale": "asks for explanation",
                    "expected_improvement": "more descriptive output",
                    "confidence": 0.8,
                }
            )
        assert "VIOLAÇÕES QUE DEVEM SER CORRIGIDAS" in prompt
        return json.dumps(
            {
                "new_prompt": (
                    "Classifique em classification. Extraia de forma literal/fiel o trecho "
                    "em text_validation. Use apenas informações presentes no input.\n{input}"
                ),
                "diff_summary": "repairs literal extraction and source constraint",
                "rationale": "preserves the task contract",
                "expected_improvement": "prevents inferred rationale",
                "preserved_invariants": ["extração literal", "não inventar"],
                "changed_behavior": ["text_validation is exact evidence"],
                "risk_of_regression": "low",
                "confidence": 0.9,
            }
        )

    initial = Prompt(
        template=(
            "Classifique a publicação e extraia o trecho exato em text_validation. "
            "Não invente informação.\n{input}"
        ),
        variables=["input"],
    )
    optimizer = Optimizer(
        config,
        target_provider=FakeProvider(target_response),
        reasoning_provider=FakeProvider(reasoning_response),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(initial, gabarito)

    assert run.stop_reason == "threshold_reached"
    assert calls["target"] == 2
    assert len(run.iterations) == 2
    assert len(run.iterations[0].refinement_repair_attempts) == 1
    assert run.iterations[1].prompt.template.startswith("Classifique em classification")


@pytest.mark.asyncio
async def test_optimize_keeps_current_prompt_when_reasoning_returns_invalid_json():
    config = _config(max_iterations=2, threshold=100)
    config.max_refinement_repair_attempts = 2
    optimizer = Optimizer(
        config,
        target_provider=FakeProvider(lambda prompt: "wrong"),
        reasoning_provider=FakeProvider(lambda prompt: ""),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.optimize(Prompt(template="{input}", variables=["input"]), _gabarito())

    assert run.stop_reason == "reasoning_failed_to_refine"
    assert len(run.iterations) == 1
    assert run.iterations[0].diagnosis is None
    assert len(run.iterations[0].refinement_repair_attempts) == 2
    assert run.iterations[0].refinement_repair_attempts[0].diff_summary == (
        "reasoning model returned invalid JSON"
    )
    assert run.best_iteration is not None
    assert run.best_iteration.prompt.template == "{input}"


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


@pytest.mark.asyncio
async def test_compare_models_records_rankings_and_case_winners():
    config = _config(max_iterations=1, threshold=100)
    config.target_model = None
    config.reasoning_model = None
    cheap = ModelSpec(
        provider="fake",
        model_id="cheap",
        role="target",
        cost_per_million_input_tokens_usd=1,
        cost_per_million_output_tokens_usd=1,
    )
    accurate = ModelSpec(
        provider="fake",
        model_id="accurate",
        role="target",
        cost_per_million_input_tokens_usd=10,
        cost_per_million_output_tokens_usd=10,
    )
    config.comparison_models = [
        ComparisonTarget(label="cheap", model=cheap),
        ComparisonTarget(label="accurate", model=accurate),
    ]
    providers = {
        "cheap": SequencedProvider(
            [CompletionResult(text="wrong", tokens_in=100, tokens_out=100)]
        ),
        "accurate": SequencedProvider(
            [CompletionResult(text="ok", tokens_in=100, tokens_out=100)]
        ),
    }

    class Factory:
        def get(self, spec):
            return providers[spec.model_id]

        def get_embedding(self, spec):
            raise NotImplementedError

    optimizer = Optimizer(
        config,
        provider_factory=Factory(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    run = await optimizer.compare_models(
        Prompt(template="{input}", variables=["input"]),
        _gabarito(),
    )

    assert run.run_mode == "compare"
    assert run.stop_reason == "comparison_completed"
    assert [iteration.comparison_label for iteration in run.iterations] == ["cheap", "accurate"]
    assert run.comparison_summary is not None
    assert run.comparison_summary.best_score.label == "accurate"
    assert run.comparison_summary.lowest_cost.label == "cheap"
    assert run.comparison_summary.case_winners[0].best_score == "accurate"


@pytest.mark.asyncio
async def test_google_provider_cache_uses_cached_context_marker():
    config = _config(max_iterations=1, threshold=100)
    config.provider_cache.enabled = True
    config.target_model = ModelSpec(provider="google", model_id="gemini-test", role="target")

    class CachedProvider:
        def __init__(self):
            self.cached_content = []
            self.calls = []

        async def create_context_cache(self, content, ttl_seconds):
            self.cached_content.append((content, ttl_seconds))
            return "cachedContents/case-1"

        async def complete_with_cached_context(self, prompt, params, cache_id):
            self.calls.append((prompt, cache_id))
            return CompletionResult(text="ok", tokens_in=10, cached_tokens_in=7, tokens_out=1)

        async def complete(self, prompt, params):
            raise AssertionError("cached context path should be used")

    provider = CachedProvider()
    optimizer = Optimizer(
        config,
        target_provider=provider,
        reasoning_provider=FakeProvider(),
        judge_provider=FakeProvider(),
        store=MemoryStore(),
        cache=MemoryCache(),
    )

    iteration = await optimizer.validate(
        Prompt(template="Responda: {input}", variables=["input"]),
        _gabarito(),
    )

    assert iteration.score == 100
    assert provider.cached_content == [("Retorne ok", 3600)]
    assert provider.calls[0][1] == "cachedContents/case-1"
    assert "Retorne ok" not in provider.calls[0][0]
    assert iteration.verdicts[0].execution.cached_tokens_in == 7
