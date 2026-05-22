from __future__ import annotations

from typing import Any

from crucible.modules.optimizer.adapters.providers.base_http import HttpProvider
from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class AnthropicAdapter(HttpProvider):
    @property
    def headers(self) -> dict[str, str]:
        headers = super().headers
        headers["anthropic-version"] = "2023-06-01"
        return headers

    @property
    def path(self) -> str:
        return "/v1/messages"

    def payload(self, prompt: str, params: ModelParams) -> dict[str, Any]:
        data = {
            "model": self.spec.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
        }
        data.update(params.extra)
        return data

    def parse(self, payload: dict[str, Any]) -> CompletionResult:
        usage = payload.get("usage") or {}
        content = payload.get("content") or []
        text = "".join(part.get("text", "") for part in content if part.get("type") == "text")
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
            finish_reason=payload.get("stop_reason") or "stop",
            raw=payload,
        )
