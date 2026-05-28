from __future__ import annotations

import ast
import json
import re
import unicodedata
from typing import Any

from crucible.modules.optimizer.domain.models import (
    ContractRule,
    Gabarito,
    ModelSpec,
    OptimizationConfig,
    Prompt,
    RefinementProposal,
    TaskContract,
)

_EXTRACTION_TERMS = (
    "exato",
    "exata",
    "literal",
    "trecho",
    "extraia",
    "extrair",
    "copie",
    "transcreva",
    "fiel",
)
_INFERENCE_DRIFT_PATTERNS = (
    "explique por que",
    "explique porque",
    "justifique por que",
    "justifique porque",
    "resuma por que",
    "inferir o motivo",
    "inferir a razão",
)
_NO_INVENTION_TERMS = (
    "não invente",
    "nao invente",
    "não criar",
    "nao criar",
    "não crie informações",
    "nao crie informacoes",
    "não inclua informação que não existe",
    "nao inclua informacao que nao existe",
    "não responda uma informação que não existe",
    "nao responda uma informacao que nao existe",
    "use apenas informações presentes",
    "use apenas informacoes presentes",
    "apenas informações presentes",
    "apenas informacoes presentes",
    "apenas nas informações presentes",
    "apenas nas informacoes presentes",
    "com base apenas nas informações presentes",
    "com base apenas nas informacoes presentes",
    "não deduza dados ausentes",
    "nao deduza dados ausentes",
    "não assuma conteúdo não mencionado",
    "nao assuma conteudo nao mencionado",
    "baseie-se apenas no texto",
    "baseie se apenas no texto",
)


def build_task_contract(
    prompt: Prompt,
    gabarito: Gabarito,
    config: OptimizationConfig,
) -> TaskContract:
    prompt_text = prompt.template.strip()
    target_model = _contract_target_model(config)
    output_schema = target_model.output_format.schema_ if target_model else {}
    output_contract = _output_contract(config)
    parsed_expected = [_parse_expected(case.expected_output) for case in gabarito.cases[:50]]
    expected_objects = [value for value in parsed_expected if isinstance(value, dict)]
    fields = _fields_from_schema(output_schema) or _fields_from_expected(expected_objects)

    invariants: list[ContractRule] = []
    negative_rules: list[ContractRule] = []
    literal_fields: list[str] = []

    if fields:
        invariants.append(
            ContractRule(
                text=f"Preservar o contrato de saída com os campos: {', '.join(fields)}.",
                source="config" if output_schema else "gabarito",
            )
        )
    if "classification" in fields:
        invariants.append(
            ContractRule(
                text="classification deve representar a classe esperada pelo gabarito/schema.",
                source="gabarito",
            )
        )
    if _contains_any(prompt_text, _EXTRACTION_TERMS):
        literal_fields.extend(_literal_fields(fields, expected_objects))
        invariants.append(
            ContractRule(
                text=(
                    "Preservar instruções de extração literal/fiel; não trocar por "
                    "explicação, resumo ou inferência."
                ),
                source="prompt",
            )
        )
    else:
        literal_fields.extend(_literal_fields(fields, expected_objects))
        if literal_fields:
            invariants.append(
                ContractRule(
                    text=(
                        "O gabarito indica que campos de evidência devem conter trecho textual "
                        "extraído/fiel, não uma justificativa inferida."
                    ),
                    source="gabarito",
                )
            )
    if _contains_any(prompt_text, ("não invente", "nao invente", "não responda uma informação")):
        negative_rules.append(
            ContractRule(
                text="Não inventar informação inexistente no input.",
                source="prompt",
            )
        )
    if re.search(r"\bfuturo", prompt_text, flags=re.IGNORECASE):
        invariants.append(
            ContractRule(
                text=(
                    "Classificar apenas eventos futuros quando essa restrição existir "
                    "no prompt inicial."
                ),
                source="prompt",
            )
        )
    if _has_empty_evidence_for_none(expected_objects):
        invariants.append(
            ContractRule(
                text="Quando classification for Nenhum, manter o campo de evidência textual vazio.",
                source="gabarito",
            )
        )

    return TaskContract(
        objective=_objective_from_prompt(prompt_text),
        output_contract=output_contract,
        invariants=_dedupe_rules(invariants),
        literal_extraction_fields=sorted(set(literal_fields)),
        negative_rules=_dedupe_rules(negative_rules),
        examples=_examples(expected_objects),
    )


def validate_refinement_against_contract(
    proposal: RefinementProposal,
    current: Prompt,
    contract: TaskContract,
) -> list[str]:
    violations = proposal.violations(current)
    new_prompt = proposal.new_prompt
    normalized = _normalize(new_prompt)
    fields = contract.output_contract.get("fields") or []

    if contract.output_contract.get("type") != "json_schema":
        for field in fields:
            if str(field) not in new_prompt and contract.literal_extraction_fields:
                violations.append(f"campo de saída ausente no prompt: {field}")

    if contract.literal_extraction_fields:
        if not _contains_any(normalized, _EXTRACTION_TERMS):
            violations.append("instrução de extração literal/fiel ausente")
        if _contains_any(normalized, _INFERENCE_DRIFT_PATTERNS):
            violations.append("proposta troca extração literal por explicação/inferência")

    if any("Não inventar" in rule.text for rule in contract.negative_rules):
        if not _contains_any(normalized, _NO_INVENTION_TERMS):
            violations.append("regra de não inventar informação foi removida")

    if any("eventos futuros" in rule.text for rule in contract.invariants):
        if "futuro" not in normalized:
            violations.append("restrição de eventos futuros foi removida")

    return violations


def _output_contract(config: OptimizationConfig) -> dict[str, Any]:
    target_model = _contract_target_model(config)
    if target_model is None:
        return {"type": "text", "name": "", "required": [], "fields": [], "enums": {}}
    output_format = target_model.output_format
    schema = output_format.schema_
    fields = _fields_from_schema(schema)
    return {
        "type": output_format.type,
        "name": output_format.name,
        "required": schema.get("required", []),
        "fields": fields,
        "enums": {
            field: spec.get("enum")
            for field, spec in (schema.get("properties") or {}).items()
            if isinstance(spec, dict) and spec.get("enum")
        },
    }


def _contract_target_model(config: OptimizationConfig) -> ModelSpec | None:
    if config.target_model is not None:
        return config.target_model
    if config.comparison_models:
        return config.comparison_models[0].model
    return None


def _fields_from_schema(schema: dict[str, Any]) -> list[str]:
    properties = schema.get("properties") or {}
    if isinstance(properties, dict):
        return list(properties.keys())
    return []


def _fields_from_expected(values: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for value in values:
        for field in value:
            if field not in fields:
                fields.append(field)
    return fields


def _literal_fields(fields: list[str], values: list[dict[str, Any]]) -> list[str]:
    literal_fields: list[str] = []
    for field in fields:
        samples = [
            str(value[field])
            for value in values
            if field in value and isinstance(value[field], str)
        ]
        non_empty = [sample for sample in samples if sample.strip()]
        if field in {"text_validation", "evidence", "quote", "excerpt", "source_text"}:
            literal_fields.append(field)
            continue
        long_samples = sum(len(sample) > 30 for sample in non_empty)
        if non_empty and long_samples >= max(1, len(non_empty) // 3):
            literal_fields.append(field)
    return literal_fields


def _parse_expected(value: str) -> Any:
    text = str(value).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def _has_empty_evidence_for_none(values: list[dict[str, Any]]) -> bool:
    for value in values:
        classification = value.get("classification")
        evidence = value.get("text_validation")
        if classification == "Nenhum" and evidence == "":
            return True
    return False


def _examples(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for value in values:
        if len(examples) >= 5:
            break
        examples.append(
            {
                key: _truncate(str(item), 240) if isinstance(item, str) else item
                for key, item in value.items()
            }
        )
    return examples


def _objective_from_prompt(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped:
            return _truncate(stripped, 240)
    return ""


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(term) in normalized for term in terms)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _dedupe_rules(rules: list[ContractRule]) -> list[ContractRule]:
    seen: set[str] = set()
    deduped: list[ContractRule] = []
    for rule in rules:
        if rule.text in seen:
            continue
        deduped.append(rule)
        seen.add(rule.text)
    return deduped
