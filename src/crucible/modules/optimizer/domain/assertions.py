from __future__ import annotations

import ast
import inspect
import json
import math
import re
from typing import Annotated, Any, Literal, Protocol

from jsonschema import ValidationError, validate
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class JudgeProvider(Protocol):
    async def complete(self, prompt: str, params: Any) -> Any: ...


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class AssertionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    judge_provider: Any | None = None
    judge_providers: list[Any] = Field(default_factory=list)
    embedding_provider: Any | None = None
    judge_params: Any = None
    judge_params_list: list[Any] = Field(default_factory=list)
    target_output_format_type: str | None = None
    target_output_schema: dict[str, Any] = Field(default_factory=dict)
    input_text: str | None = None


class AssertionResult(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    detail: dict[str, Any] = Field(default_factory=dict)


class BaseAssertion(BaseModel):
    type: str

    async def evaluate(
        self,
        expected: str,
        actual: str,
        context: AssertionContext,
    ) -> AssertionResult:
        raise NotImplementedError


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())


_JSON_SCHEMA_KEYWORDS = {
    "$defs",
    "$id",
    "$ref",
    "$schema",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "contains",
    "dependentRequired",
    "dependentSchemas",
    "description",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "items",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "not",
    "oneOf",
    "pattern",
    "patternProperties",
    "prefixItems",
    "properties",
    "propertyNames",
    "required",
    "title",
    "type",
    "uniqueItems",
}


def _load_json(value: str) -> Any:
    text = _unwrap_json_text(value)
    candidates = [text]
    extracted = _extract_json_like(text)
    if extracted is not None and extracted != text:
        candidates.append(extracted)

    first_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
        try:
            return ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            continue
    if first_error is not None:
        raise first_error
    raise json.JSONDecodeError("invalid structured value", text, 0)


def _unwrap_json_text(value: str) -> str:
    text = str(value).strip()
    match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1).strip() if match else text


def _extract_json_like(value: str) -> str | None:
    object_start = value.find("{")
    array_start = value.find("[")
    starts = [index for index in (object_start, array_start) if index >= 0]
    if not starts:
        return None
    start = min(starts)
    close_char = "}" if value[start] == "{" else "]"
    end = value.rfind(close_char)
    if end <= start:
        return None
    return value[start : end + 1].strip()


def _looks_like_json_schema(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if not isinstance(value, dict):
        return False
    return not value or bool(_JSON_SCHEMA_KEYWORDS.intersection(value))


def _not_json_schema_result() -> AssertionResult:
    return AssertionResult(
        score=0.0,
        passed=False,
        detail={
            "error": "expected_output_must_be_json_schema",
            "hint": (
                "Use json_equal or field_by_field when expected_output is "
                "the expected JSON payload."
            ),
        },
    )



def _compare_objects(expected: dict[str, Any], actual: dict[str, Any]) -> AssertionResult:
    fields = list(expected.keys())
    if not fields:
        return AssertionResult(score=1.0, passed=True)

    matched = sum(1 for field in fields if actual.get(field) == expected[field])
    score = matched / len(fields)
    return AssertionResult(
        score=score,
        passed=math.isclose(score, 1.0),
        detail={"fields": fields, "comparison_mode": "field_by_field"},
    )


class ExactMatch(BaseAssertion):
    type: Literal["exact_match"] = "exact_match"
    normalize: bool = True
    case_sensitive: bool = True

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        left = _normalize(expected) if self.normalize else expected
        right = _normalize(actual) if self.normalize else actual
        if not self.case_sensitive:
            left = left.lower()
            right = right.lower()
        passed = left == right
        return AssertionResult(score=1.0 if passed else 0.0, passed=passed)


class Contains(BaseAssertion):
    type: Literal["contains"] = "contains"
    case_sensitive: bool = False

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        needle = expected if self.case_sensitive else expected.lower()
        haystack = actual if self.case_sensitive else actual.lower()
        passed = needle in haystack
        return AssertionResult(score=1.0 if passed else 0.0, passed=passed)


class Regex(BaseAssertion):
    type: Literal["regex"] = "regex"
    pattern: str | None = None
    flags: int = 0

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        pattern = self.pattern or expected
        passed = re.search(pattern, actual, self.flags) is not None
        return AssertionResult(
            score=1.0 if passed else 0.0,
            passed=passed,
            detail={"pattern": pattern},
        )


class NumericMatch(BaseAssertion):
    type: Literal["numeric_match"] = "numeric_match"
    tolerance: float = 0.0

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        try:
            expected_number = float(str(expected).replace(",", "."))
            actual_number = float(str(actual).replace(",", "."))
        except ValueError:
            return AssertionResult(score=0.0, passed=False, detail={"error": "invalid_number"})

        delta = abs(expected_number - actual_number)
        passed = delta <= self.tolerance
        score = 1.0 if passed else max(0.0, 1.0 - (delta / (abs(expected_number) or 1.0)))
        return AssertionResult(score=score, passed=passed, detail={"delta": delta})


class JsonEqual(BaseAssertion):
    type: Literal["json_equal"] = "json_equal"

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        try:
            expected_json = _load_json(expected)
            actual_json = _load_json(actual)
        except ValueError as exc:
            return AssertionResult(score=0.0, passed=False, detail={"error": str(exc)})
        passed = expected_json == actual_json
        return AssertionResult(score=1.0 if passed else 0.0, passed=passed)


class JsonSchema(BaseAssertion):
    type: Literal["json_schema"] = "json_schema"
    json_schema: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("json_schema", "schema"),
    )

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        try:
            schema = self.json_schema
            expected_json = None
            if schema is None:
                expected_json = _load_json(expected)
                schema = expected_json if _looks_like_json_schema(expected_json) else None
            if schema is None:
                if (
                    context.target_output_format_type == "json_schema"
                    and context.target_output_schema
                ):
                    actual_json = _load_json(actual)
                    validate(instance=expected_json, schema=context.target_output_schema)
                    validate(instance=actual_json, schema=context.target_output_schema)
                    if isinstance(expected_json, dict) and isinstance(actual_json, dict):
                        result = _compare_objects(expected_json, actual_json)
                    else:
                        passed = expected_json == actual_json
                        result = AssertionResult(score=1.0 if passed else 0.0, passed=passed)
                    result.detail["schema_source"] = "target_output_format"
                    return result
                return _not_json_schema_result()
            validate(instance=_load_json(actual), schema=schema)
        except (ValueError, ValidationError) as exc:
            return AssertionResult(score=0.0, passed=False, detail={"error": str(exc)})
        return AssertionResult(score=1.0, passed=True)


class FieldAssertionSpec(BaseModel):
    type: Literal[
        "exact",
        "normalized_exact",
        "contains",
        "embedding_similarity",
        "llm_judge",
    ] = "exact"
    threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    case_sensitive: bool = False
    bidirectional: bool = True
    rubric: str = ""
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    position_swap: bool = False


class FieldByField(BaseAssertion):
    type: Literal["field_by_field"] = "field_by_field"
    weights: dict[str, float] = Field(default_factory=dict)
    field_assertions: dict[str, FieldAssertionSpec] = Field(default_factory=dict)

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        try:
            expected_json = _load_json(expected)
            actual_json = _load_json(actual)
        except ValueError as exc:
            return AssertionResult(score=0.0, passed=False, detail={"error": str(exc)})
        if not isinstance(expected_json, dict) or not isinstance(actual_json, dict):
            return AssertionResult(score=0.0, passed=False, detail={"error": "expected_objects"})

        fields = list(expected_json.keys())
        if not fields:
            return AssertionResult(score=1.0, passed=True)

        field_results: dict[str, dict[str, Any]] = {}
        total_weight = 0.0
        weighted_score = 0.0
        passed = True
        for field in fields:
            weight = self.weights.get(field, 1.0)
            total_weight += weight
            result = await _evaluate_field(
                field=field,
                expected=expected_json[field],
                actual=actual_json.get(field),
                actual_missing=field not in actual_json,
                spec=self.field_assertions.get(field, FieldAssertionSpec()),
                context=context,
            )
            weighted_score += weight * result.score
            passed = passed and result.passed
            field_results[field] = result.detail | {
                "score": result.score,
                "passed": result.passed,
                "weight": weight,
            }
        score = weighted_score / total_weight if total_weight else 0.0
        return AssertionResult(
            score=score,
            passed=passed,
            detail={"fields": fields, "field_results": field_results},
        )


async def _evaluate_field(
    field: str,
    expected: Any,
    actual: Any,
    actual_missing: bool,
    spec: FieldAssertionSpec,
    context: AssertionContext,
) -> AssertionResult:
    if actual_missing:
        return AssertionResult(
            score=0.0,
            passed=False,
            detail={"type": spec.type, "error": "missing_field"},
        )
    expected_text = _field_value_text(expected)
    actual_text = _field_value_text(actual)
    if spec.type == "exact":
        passed = actual == expected
        return AssertionResult(
            score=1.0 if passed else 0.0,
            passed=passed,
            detail={"type": spec.type},
        )
    if spec.type == "normalized_exact":
        left = _normalize(expected_text)
        right = _normalize(actual_text)
        if not spec.case_sensitive:
            left = left.lower()
            right = right.lower()
        passed = left == right
        return AssertionResult(
            score=1.0 if passed else 0.0,
            passed=passed,
            detail={"type": spec.type},
        )
    if spec.type == "contains":
        left = expected_text if spec.case_sensitive else expected_text.lower()
        right = actual_text if spec.case_sensitive else actual_text.lower()
        passed = left in right or (spec.bidirectional and right in left)
        return AssertionResult(
            score=1.0 if passed else 0.0,
            passed=passed,
            detail={"type": spec.type, "bidirectional": spec.bidirectional},
        )
    if spec.type == "embedding_similarity":
        result = await EmbeddingSimilarity(threshold=spec.threshold).evaluate(
            expected_text,
            actual_text,
            context,
        )
        result.detail = result.detail | {"type": spec.type, "threshold": spec.threshold}
        return result
    if spec.type == "llm_judge":
        threshold = spec.pass_threshold if spec.pass_threshold is not None else spec.threshold
        result = await LLMJudge(
            rubric=_field_judge_rubric(field, spec),
            pass_threshold=threshold,
            position_swap=spec.position_swap,
        ).evaluate(
            _field_judge_expected(field, expected_text, context),
            actual_text,
            context,
        )
        result.detail = result.detail | {"type": spec.type, "threshold": threshold}
        return result
    return AssertionResult(score=0.0, passed=False, detail={"error": "unknown_field_assertion"})


def _field_value_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _field_judge_rubric(field: str, spec: FieldAssertionSpec) -> str:
    if spec.rubric.strip():
        return spec.rubric
    return (
        f"Avalie o campo '{field}'. A resposta atual deve ser equivalente ao valor esperado. "
        "Se houver input original no esperado, verifique também se a resposta atual está "
        "apoiada pelo texto fonte e não inventa informação."
    )


def _field_judge_expected(field: str, expected: str, context: AssertionContext) -> str:
    if context.input_text is None:
        return expected
    return (
        f"Campo: {field}\n"
        f"Valor esperado:\n{expected}\n\n"
        f"Input original:\n{context.input_text}"
    )


class PydanticModel(BaseAssertion):
    type: Literal["pydantic_model"] = "pydantic_model"
    json_schema: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("json_schema", "schema"),
    )

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        schema_result = await JsonSchema(json_schema=self.json_schema).evaluate(
            expected, actual, context
        )
        if not schema_result.passed:
            return schema_result
        return await FieldByField().evaluate(expected, actual, context)


class EmbeddingSimilarity(BaseAssertion):
    type: Literal["embedding_similarity"] = "embedding_similarity"
    threshold: float = 0.85

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        if context.embedding_provider is None:
            return AssertionResult(
                score=0.0, passed=False, detail={"error": "missing_embedding_provider"}
            )
        expected_vec, actual_vec = await context.embedding_provider.embed([expected, actual])
        score = _cosine(expected_vec, actual_vec)
        return AssertionResult(score=score, passed=score >= self.threshold)


class LLMJudge(BaseAssertion):
    type: Literal["llm_judge"] = "llm_judge"
    rubric: str
    pass_threshold: float = 0.7
    position_swap: bool = True
    calibration_examples: list[dict[str, Any]] = Field(default_factory=list)

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        providers = context.judge_providers or (
            [context.judge_provider] if context.judge_provider is not None else []
        )
        if not providers:
            return AssertionResult(
                score=0.0, passed=False, detail={"error": "missing_judge_provider"}
            )
        params_list = context.judge_params_list or [context.judge_params] * len(providers)
        payloads: list[dict[str, Any]] = []
        for provider, params in zip(providers, params_list, strict=False):
            payloads.append(
                await self._safe_judge(provider, params, expected, actual, swapped=False)
            )
            if self.position_swap:
                payloads.append(
                    await self._safe_judge(provider, params, expected, actual, swapped=True)
                )
        score = sum(float(payload.get("score", 0.0)) for payload in payloads) / len(payloads)
        passed_votes = sum(
            1 for payload in payloads if bool(payload.get("passed", score >= self.pass_threshold))
        )
        passed = passed_votes >= (len(payloads) / 2) and score >= self.pass_threshold
        return AssertionResult(
            score=max(0.0, min(1.0, score)),
            passed=passed,
            detail={"judges": payloads, "passed_votes": passed_votes, "judge_count": len(payloads)},
        )

    async def _safe_judge(
        self,
        provider: Any,
        params: Any,
        expected: str,
        actual: str,
        swapped: bool,
    ) -> dict[str, Any]:
        try:
            return await self._judge(provider, params, expected, actual, swapped)
        except Exception as exc:
            return {
                "score": 0.0,
                "passed": False,
                "rationale": "Judge returned an invalid response or failed during evaluation.",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "swapped": swapped,
            }

    async def _judge(
        self,
        provider: Any,
        params: Any,
        expected: str,
        actual: str,
        swapped: bool,
    ) -> dict[str, Any]:
        left_label = "Atual" if swapped else "Esperado"
        right_label = "Esperado" if swapped else "Atual"
        left = actual if swapped else expected
        right = expected if swapped else actual
        prompt = (
            "Avalie se a resposta atual atende ao esperado.\n"
            f"Rubrica: {self.rubric}\n"
            f"Calibration examples: {json.dumps(self.calibration_examples, ensure_ascii=False)}\n\n"
            f"{left_label}:\n{left}\n\n"
            f"{right_label}:\n{right}\n\n"
            'Retorne JSON estrito: {"score": 0.0, "passed": false, "rationale": "..."}'
        )
        result = await provider.complete(prompt, params)
        payload = _parse_judge_payload(result.text)
        payload["swapped"] = swapped
        return payload


class LLMJudgeWithRationale(LLMJudge):
    type: Literal["llm_judge_with_rationale"] = "llm_judge_with_rationale"  # type: ignore[assignment]


class PluginAssertion(BaseAssertion):
    type: Literal["plugin"] = "plugin"
    name: str
    config: dict[str, Any] = Field(default_factory=dict)

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        from crucible.modules.optimizer.plugins.registry import get_plugin_registry

        handler = get_plugin_registry().assertions.get(self.name)
        if handler is None:
            return AssertionResult(
                score=0.0,
                passed=False,
                detail={"error": f"plugin assertion not registered: {self.name}"},
            )
        result = handler(expected, actual, self.config, context)
        if inspect.isawaitable(result):
            result = await result
        return result


Assertion = Annotated[
    ExactMatch
    | Contains
    | Regex
    | NumericMatch
    | JsonEqual
    | JsonSchema
    | FieldByField
    | PydanticModel
    | EmbeddingSimilarity
    | LLMJudge
    | LLMJudgeWithRationale
    | PluginAssertion,
    Field(discriminator="type"),
]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _parse_judge_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not cleaned:
        raise ValueError("judge_returned_empty_response")
    return json.loads(cleaned)
