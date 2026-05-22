import pytest

from crucible.modules.optimizer.domain.assertions import (
    AssertionContext,
    Contains,
    EmbeddingSimilarity,
    ExactMatch,
    FieldByField,
    JsonEqual,
    JsonSchema,
    LLMJudge,
    NumericMatch,
    PluginAssertion,
    PydanticModel,
    Regex,
)
from crucible.modules.optimizer.domain.models import CompletionResult


@pytest.mark.asyncio
async def test_exact_match_normalizes_whitespace():
    result = await ExactMatch().evaluate("a b", " a   b ", AssertionContext())
    assert result.passed is True
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_contains_is_case_insensitive_by_default():
    result = await Contains().evaluate("OK", "status: ok", AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_regex_uses_expected_as_pattern_when_pattern_missing():
    result = await Regex().evaluate(r"\d{3}", "abc 123", AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_numeric_match_scores_with_tolerance():
    result = await NumericMatch(tolerance=0.1).evaluate("10", "10.05", AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_json_equal_compares_structures():
    result = await JsonEqual().evaluate('{"a": 1}', '{"a": 1}', AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_field_by_field_returns_partial_score():
    result = await FieldByField().evaluate(
        '{"a": 1, "b": 2}', '{"a": 1, "b": 3}', AssertionContext()
    )
    assert result.passed is False
    assert result.score == 0.5


@pytest.mark.asyncio
async def test_json_schema_accepts_schema_alias():
    assertion = JsonSchema.model_validate(
        {"type": "json_schema", "schema": {"type": "object", "required": ["ok"]}}
    )
    result = await assertion.evaluate("", '{"ok": true}', AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_pydantic_model_validates_schema_then_fields():
    assertion = PydanticModel(json_schema={"type": "object", "required": ["ok"]})
    result = await assertion.evaluate('{"ok": true}', '{"ok": true}', AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_embedding_similarity_uses_provider():
    class Embedder:
        async def embed(self, texts):
            return [[1.0, 0.0], [1.0, 0.0]]

    result = await EmbeddingSimilarity().evaluate(
        "", "", AssertionContext(embedding_provider=Embedder())
    )
    assert result.passed is True


@pytest.mark.asyncio
async def test_llm_judge_parses_json_response():
    class Judge:
        async def complete(self, prompt, params):
            return CompletionResult(text='{"score": 0.8, "passed": true, "rationale": "ok"}')

    result = await LLMJudge(rubric="compare").evaluate(
        "expected",
        "actual",
        AssertionContext(judge_provider=Judge()),
    )
    assert result.passed is True
    assert result.score == 0.8


@pytest.mark.asyncio
async def test_plugin_assertion_uses_registry():
    from crucible.modules.optimizer.plugins.registry import get_plugin_registry

    async def async_handler(expected, actual, config, context):
        from crucible.modules.optimizer.domain.assertions import AssertionResult

        return AssertionResult(score=1.0, passed=True, detail={"plugin": config["value"]})

    registry = get_plugin_registry()
    registry.register_assertion("custom", async_handler)

    result = await PluginAssertion(name="custom", config={"value": "ok"}).evaluate(
        "a", "b", AssertionContext()
    )

    assert result.passed is True
    assert result.detail["plugin"] == "ok"
