from __future__ import annotations

from typing import Any

from crucible.modules.optimizer.adapters.providers.base_http import HttpProvider
from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class LlamaCppAdapter(HttpProvider):
    @property
    def path(self) -> str:
        return "/completion"

    def payload(self, prompt: str, params: ModelParams) -> dict[str, Any]:
        data: dict[str, Any] = {
            "prompt": prompt,
            "temperature": params.temperature,
            "n_predict": params.max_tokens,
        }
        if self.spec.output_format.type == "json_object":
            data["response_format"] = {"type": "json_object"}
        elif self.spec.output_format.type == "json_schema":
            data["response_format"] = {
                "type": "json_schema",
                "schema": self.spec.output_format.schema_,
            }
        data.update(params.extra)
        return data

    def parse(self, payload: dict[str, Any]) -> CompletionResult:
        return CompletionResult(
            text=payload.get("content", ""),
            tokens_in=int(payload.get("tokens_evaluated") or 0),
            tokens_out=int(payload.get("tokens_predicted") or 0),
            finish_reason=payload.get("stop_type") or "stop",
            raw=payload,
        )
