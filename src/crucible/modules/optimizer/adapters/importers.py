from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from crucible.modules.optimizer.domain.assertions import Contains, ExactMatch, JsonSchema, Regex
from crucible.modules.optimizer.domain.models import Gabarito, TestCase
from crucible.modules.optimizer.plugins.registry import get_plugin_registry


def import_gabarito(path: Path, source: str) -> Gabarito:
    text = path.read_text(encoding="utf-8")
    registry = get_plugin_registry()
    if source in registry.importers:
        return registry.importers[source](text)
    if source == "jsonl":
        return import_jsonl(text, name=path.stem)
    if source == "promptfoo":
        return import_promptfoo(text, name=path.stem)
    if source == "langsmith":
        return import_langsmith(text, name=path.stem)
    if source == "dspy":
        return import_dspy(text, name=path.stem)
    raise ValueError(f"Unsupported importer: {source}")


def import_jsonl(text: str, name: str = "jsonl-import") -> Gabarito:
    cases = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        cases.append(_case_from_mapping(payload, default_id=f"case-{index:03d}"))
    return Gabarito(name=name, version="imported", cases=cases)


def import_promptfoo(text: str, name: str = "promptfoo-import") -> Gabarito:
    payload = yaml.safe_load(text)
    tests = payload.get("tests") or payload.get("prompts", []) if isinstance(payload, dict) else []
    cases = []
    for index, item in enumerate(tests, start=1):
        if not isinstance(item, dict):
            continue
        variables = item.get("vars", {}) or {}
        assertions = item.get("assert") or item.get("assertions") or []
        if isinstance(assertions, dict):
            assertions = [assertions]
        expected = _expected_from_assertions(assertions)
        cases.append(
            TestCase(
                id=item.get("id", f"case-{index:03d}"),
                input=_input_from_variables(variables),
                expected_output=expected,
                assertion=_assertion_from_promptfoo(assertions),
                tags=_tags(item.get("tags")),
            )
        )
    return Gabarito(name=name, version="promptfoo", cases=cases)


def import_langsmith(text: str, name: str = "langsmith-import") -> Gabarito:
    payload = json.loads(text)
    examples = _examples_from_payload(payload)
    return Gabarito(
        name=name,
        version="langsmith",
        cases=[
            _case_from_mapping(item, default_id=f"case-{index:03d}")
            for index, item in enumerate(examples, 1)
        ],
    )


def import_dspy(text: str, name: str = "dspy-import") -> Gabarito:
    payload = json.loads(text)
    examples = _examples_from_payload(payload)
    return Gabarito(
        name=name,
        version="dspy",
        cases=[
            _case_from_mapping(item, default_id=f"case-{index:03d}")
            for index, item in enumerate(examples, 1)
        ],
    )


def _case_from_mapping(payload: dict[str, Any], default_id: str) -> TestCase:
    input_value = (
        payload.get("input")
        or payload.get("inputs")
        or payload.get("question")
        or payload.get("prompt")
        or payload.get("x")
        or ""
    )
    output_value = (
        payload.get("expected_output")
        or payload.get("expected")
        or payload.get("output")
        or payload.get("outputs")
        or payload.get("answer")
        or payload.get("label")
        or payload.get("y")
        or ""
    )
    if isinstance(input_value, dict):
        input_value = (
            input_value.get("input") or input_value.get("question") or json.dumps(input_value)
        )
    if isinstance(output_value, dict):
        output_value = (
            output_value.get("output")
            or output_value.get("answer")
            or output_value.get("expected")
            or next(iter(output_value.values()), "")
            or json.dumps(output_value)
        )
    return TestCase(
        id=str(payload.get("id") or payload.get("example_id") or payload.get("uuid") or default_id),
        input=str(input_value),
        expected_output=str(output_value),
        assertion=Contains(),
        tags=_tags(payload.get("tags") or payload.get("metadata", {}).get("tags")),
    )


def _expected_from_assertions(assertions: list[dict[str, Any]]) -> str:
    for assertion in assertions:
        if isinstance(assertion, dict) and "value" in assertion:
            return str(assertion["value"])
        if isinstance(assertion, dict) and "expected" in assertion:
            return str(assertion["expected"])
    return ""


def _examples_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("examples", "data", "rows", "trainset", "devset", "demos"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _input_from_variables(variables: Any) -> str:
    if not isinstance(variables, dict):
        return str(variables)
    return str(
        variables.get("input")
        or variables.get("question")
        or variables.get("query")
        or variables.get("prompt")
        or json.dumps(variables, ensure_ascii=False, sort_keys=True)
    )


def _assertion_from_promptfoo(assertions: list[dict[str, Any]]):
    first = next((item for item in assertions if isinstance(item, dict)), {})
    assertion_type = str(first.get("type", "")).lower()
    if assertion_type in {"equals", "exact", "exact_match", "is-equal"}:
        return ExactMatch()
    if assertion_type in {"regex", "matches"}:
        return Regex(pattern=str(first.get("value", "")) or None)
    if assertion_type in {"javascript", "python"}:
        return ExactMatch()
    if assertion_type in {"is-json", "json_schema", "json-schema"}:
        schema = first.get("schema") or first.get("value")
        return JsonSchema(json_schema=schema if isinstance(schema, dict) else None)
    return Contains() if _expected_from_assertions(assertions) else ExactMatch()


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if enabled]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
