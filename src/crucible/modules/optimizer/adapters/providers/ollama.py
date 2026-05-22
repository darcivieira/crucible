from __future__ import annotations

from typing import Any

from crucible.modules.optimizer.adapters.providers.base_http import HttpProvider
from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class OllamaAdapter(HttpProvider):
    @property
    def path(self) -> str:
        return "/api/generate"

    def payload(self, prompt: str, params: ModelParams) -> dict[str, Any]:
        data: dict[str, Any] = {
            "model": self.spec.model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
            },
        }
        if params.seed is not None:
            data["options"]["seed"] = params.seed
        data.update(params.extra)
        return data

    def parse(self, payload: dict[str, Any]) -> CompletionResult:
        return CompletionResult(
            text=payload.get("response", ""),
            tokens_in=int(payload.get("prompt_eval_count") or 0),
            tokens_out=int(payload.get("eval_count") or 0),
            finish_reason=payload.get("done_reason") or "stop",
            raw=payload,
        )
