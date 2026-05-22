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
