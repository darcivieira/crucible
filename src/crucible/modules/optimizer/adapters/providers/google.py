from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from crucible.modules.optimizer.adapters.providers.base_http import HttpProvider, _response_json
from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class GoogleAdapter(HttpProvider):
    @property
    def path(self) -> str:
        return f"/v1beta/models/{self.spec.model_id}:generateContent"

    @property
    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key} if self.api_key else {}

    async def create_context_cache(self, content: str, ttl_seconds: int) -> str:
        payload = {
            "model": f"models/{self.spec.model_id}",
            "contents": [{"parts": [{"text": content}]}],
            "ttl": f"{ttl_seconds}s",
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(
                "/v1beta/cachedContents",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = _response_json(
                response,
                provider=self.spec.provider,
                model_id=self.spec.model_id,
                path="/v1beta/cachedContents",
            )
        return str(data["name"])

    async def complete_with_cached_context(
        self,
        prompt: str,
        params: ModelParams,
        cache_id: str,
    ) -> CompletionResult:
        started = perf_counter()
        payload = self.payload(prompt, params)
        payload["cachedContent"] = cache_id
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(self.path, headers=self.headers, json=payload)
            response.raise_for_status()
            data = _response_json(
                response,
                provider=self.spec.provider,
                model_id=self.spec.model_id,
                path=self.path,
            )
        result = self.parse(data)
        result.raw["provider_cache_id"] = cache_id
        result.raw["latency_ms"] = (perf_counter() - started) * 1000
        return result

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
            cached_tokens_in=int(usage.get("cachedContentTokenCount") or 0),
            tokens_out=int(usage.get("candidatesTokenCount") or 0),
            finish_reason=candidates[0].get("finishReason") or "stop",
            raw=payload,
        )
