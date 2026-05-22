from __future__ import annotations

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


def _load_json(value: str) -> Any:
    return json.loads(value)


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
        except json.JSONDecodeError as exc:
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
            schema = self.json_schema or _load_json(expected)
            validate(instance=_load_json(actual), schema=schema)
        except (json.JSONDecodeError, ValidationError) as exc:
            return AssertionResult(score=0.0, passed=False, detail={"error": str(exc)})
        return AssertionResult(score=1.0, passed=True)


class FieldByField(BaseAssertion):
    type: Literal["field_by_field"] = "field_by_field"
    weights: dict[str, float] = Field(default_factory=dict)

    async def evaluate(
        self, expected: str, actual: str, context: AssertionContext
    ) -> AssertionResult:
        try:
            expected_json = _load_json(expected)
            actual_json = _load_json(actual)
        except json.JSONDecodeError as exc:
            return AssertionResult(score=0.0, passed=False, detail={"error": str(exc)})
        if not isinstance(expected_json, dict) or not isinstance(actual_json, dict):
            return AssertionResult(score=0.0, passed=False, detail={"error": "expected_objects"})

        fields = list(expected_json.keys())
        if not fields:
            return AssertionResult(score=1.0, passed=True)

        total_weight = sum(self.weights.get(field, 1.0) for field in fields)
        matched_weight = sum(
            self.weights.get(field, 1.0)
            for field in fields
            if actual_json.get(field) == expected_json[field]
        )
        score = matched_weight / total_weight
        return AssertionResult(
            score=score,
            passed=math.isclose(score, 1.0),
            detail={"fields": fields},
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
            payloads.append(await self._judge(provider, params, expected, actual, swapped=False))
            if self.position_swap:
                payloads.append(await self._judge(provider, params, expected, actual, swapped=True))
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
    return json.loads(cleaned)
