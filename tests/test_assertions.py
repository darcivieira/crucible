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
async def test_json_equal_accepts_json_like_strings():
    result = await JsonEqual().evaluate(
        "{'classification': 'Prazo'}",
        "```json\n{'classification': 'Prazo'}\n```",
        AssertionContext(),
    )
    assert result.passed is True


@pytest.mark.asyncio
async def test_field_by_field_returns_partial_score():
    result = await FieldByField().evaluate(
        '{"a": 1, "b": 2}', '{"a": 1, "b": 3}', AssertionContext()
    )
    assert result.passed is False
    assert result.score == 0.5
    assert result.detail["field_results"]["a"]["type"] == "exact"


@pytest.mark.asyncio
async def test_field_by_field_supports_per_field_assertions():
    assertion = FieldByField.model_validate(
        {
            "type": "field_by_field",
            "weights": {"classification": 95, "text_validation": 5},
            "field_assertions": {
                "classification": {"type": "exact"},
                "text_validation": {"type": "normalized_exact", "case_sensitive": False},
            },
        }
    )

    result = await assertion.evaluate(
        '{"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}',
        '{"classification": "Prazo", "text_validation": "  intime-se   no PRAZO de 5 dias. "}',
        AssertionContext(),
    )

    assert result.passed is True
    assert result.score == 1.0
    assert result.detail["field_results"]["text_validation"]["type"] == "normalized_exact"


@pytest.mark.asyncio
async def test_field_by_field_scores_qualitative_fields_with_weights():
    assertion = FieldByField.model_validate(
        {
            "type": "field_by_field",
            "weights": {"classification": 95, "text_validation": 5},
            "field_assertions": {
                "classification": {"type": "exact"},
                "text_validation": {"type": "contains"},
            },
        }
    )

    result = await assertion.evaluate(
        '{"classification": "Prazo", "text_validation": "prazo de 5 dias"}',
        '{"classification": "Prazo", "text_validation": "Intime-se no prazo de 5 dias."}',
        AssertionContext(),
    )

    assert result.passed is True
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_field_by_field_uses_embedding_similarity_per_field():
    class Embedder:
        async def embed(self, texts):
            return [[1.0, 0.0], [1.0, 0.0]]

    assertion = FieldByField.model_validate(
        {
            "type": "field_by_field",
            "field_assertions": {
                "text_validation": {"type": "embedding_similarity", "threshold": 0.9}
            },
        }
    )

    result = await assertion.evaluate(
        '{"text_validation": "prazo de 5 dias"}',
        '{"text_validation": "o prazo concedido foi de cinco dias"}',
        AssertionContext(embedding_provider=Embedder()),
    )

    assert result.passed is True
    assert result.detail["field_results"]["text_validation"]["type"] == "embedding_similarity"


@pytest.mark.asyncio
async def test_field_by_field_llm_judge_receives_original_input():
    class Judge:
        prompts = []

        async def complete(self, prompt, params):
            self.prompts.append(prompt)
            return CompletionResult(text='{"score": 0.9, "passed": true, "rationale": "ok"}')

    judge = Judge()
    assertion = FieldByField.model_validate(
        {
            "type": "field_by_field",
            "field_assertions": {
                "text_validation": {
                    "type": "llm_judge",
                    "threshold": 0.8,
                    "rubric": "Verifique se o trecho existe no input original.",
                }
            },
        }
    )

    result = await assertion.evaluate(
        '{"text_validation": "prazo de 5 dias"}',
        '{"text_validation": "prazo de 5 dias"}',
        AssertionContext(judge_provider=judge, input_text="Intime-se no prazo de 5 dias."),
    )

    assert result.passed is True
    assert "Input original" in judge.prompts[0]
    assert "Intime-se no prazo de 5 dias." in judge.prompts[0]


@pytest.mark.asyncio
async def test_field_by_field_extracts_json_like_payload_from_text():
    result = await FieldByField().evaluate(
        "{'classification': 'Prazo', 'text_validation': 'Intime-se.'}",
        "Resposta:\n{'classification': 'Prazo', 'text_validation': 'Intime-se.'}",
        AssertionContext(),
    )
    assert result.passed is True


@pytest.mark.asyncio
async def test_json_schema_accepts_schema_alias():
    assertion = JsonSchema.model_validate(
        {"type": "json_schema", "schema": {"type": "object", "required": ["ok"]}}
    )
    result = await assertion.evaluate("", '{"ok": true}', AssertionContext())
    assert result.passed is True


@pytest.mark.asyncio
async def test_json_schema_rejects_expected_payload_as_schema():
    result = await JsonSchema().evaluate(
        "{'classification': 'Prazo'}",
        "{'classification': 'Prazo'}",
        AssertionContext(),
    )
    assert result.passed is False
    assert result.detail["error"] == "expected_output_must_be_json_schema"


@pytest.mark.asyncio
async def test_json_schema_compares_expected_payload_when_output_schema_is_configured():
    context = AssertionContext(
        target_output_format_type="json_schema",
        target_output_schema={
            "type": "object",
            "required": ["classification", "text_validation"],
            "properties": {
                "classification": {"type": "string"},
                "text_validation": {"type": "string"},
            },
        },
    )

    result = await JsonSchema().evaluate(
        "{'classification': 'Prazo', 'text_validation': 'Intime-se.'}",
        "Resposta:\n{'classification': 'Prazo', 'text_validation': 'Intime-se.'}",
        context,
    )

    assert result.passed is True
    assert result.detail["schema_source"] == "target_output_format"
    assert result.detail["comparison_mode"] == "field_by_field"


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
