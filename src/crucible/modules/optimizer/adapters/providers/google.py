from __future__ import annotations

from typing import Any

from crucible.modules.optimizer.adapters.providers.base_http import HttpProvider
from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class GoogleAdapter(HttpProvider):
    @property
    def path(self) -> str:
        return f"/v1beta/models/{self.spec.model_id}:generateContent"

    @property
    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key} if self.api_key else {}

    def payload(self, prompt: str, params: ModelParams) -> dict[str, Any]:
        data: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": params.temperature,
                "maxOutputTokens": params.max_tokens,
            },
        }
        if self.spec.output_format.type in {"json_object", "json_schema"}:
            data["generationConfig"]["responseMimeType"] = "application/json"
        if self.spec.output_format.type == "json_schema":
            data["generationConfig"]["responseSchema"] = self.spec.output_format.schema_
        data.update(params.extra)
        return data

    def parse(self, payload: dict[str, Any]) -> CompletionResult:
        candidates = payload.get("candidates") or [{}]
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)
        usage = payload.get("usageMetadata") or {}
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("promptTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0),
            finish_reason=candidates[0].get("finishReason") or "stop",
            raw=payload,
        )
