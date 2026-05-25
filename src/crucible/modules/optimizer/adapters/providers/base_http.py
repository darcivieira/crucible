from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

import httpx

from crucible.core.exceptions import ProviderError
from crucible.modules.optimizer.domain.models import (
    CompletionResult,
    ModelOutputFormat,
    ModelParams,
    ModelSpec,
)


class HttpProvider:
    def __init__(
        self,
        spec: ModelSpec,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 300.0,
    ):
        self.spec = spec
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        if self.api_key is None:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    async def complete(self, prompt: str, params: ModelParams) -> CompletionResult:
        started = perf_counter()
        last_error: httpx.HTTPError | None = None
        try:
            for attempt in range(self.spec.rate_limit.retry_attempts + 1):
                try:
                    async with httpx.AsyncClient(
                        base_url=self.base_url, timeout=self.timeout
                    ) as client:
                        response = await client.post(
                            self.path,
                            headers=self.headers,
                            json=self.payload(prompt, params),
                        )
                        response.raise_for_status()
                        payload = response.json()
                        break
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code not in {429, 500, 502, 503, 504}:
                        raise
                    if attempt >= self.spec.rate_limit.retry_attempts:
                        raise
                    await asyncio.sleep(self.spec.rate_limit.retry_backoff_seconds * (2**attempt))
                except httpx.HTTPError as exc:
                    last_error = exc
                    if attempt >= self.spec.rate_limit.retry_attempts:
                        raise
                    await asyncio.sleep(self.spec.rate_limit.retry_backoff_seconds * (2**attempt))
        except httpx.HTTPError as exc:
            raise ProviderError(_provider_error_message(self.spec.provider, exc)) from exc
        if last_error is not None and "payload" not in locals():
            raise ProviderError(f"{self.spec.provider} provider request failed: {last_error}")
        result = self.parse(payload)
        result.raw.setdefault("latency_ms", (perf_counter() - started) * 1000)
        return result

    @property
    def path(self) -> str:
        return "/v1/chat/completions"

    def payload(self, prompt: str, params: ModelParams) -> dict[str, Any]:
        data = {
            "model": self.spec.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.top_p is not None:
            data["top_p"] = params.top_p
        output_format = _chat_response_format(self.spec.output_format)
        if output_format is not None:
            data["response_format"] = output_format
        data.update(params.extra)
        return data

    def parse(self, payload: dict[str, Any]) -> CompletionResult:
        usage = payload.get("usage") or {}
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or choice.get("text") or ""
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            finish_reason=choice.get("finish_reason") or "stop",
            raw=payload,
        )


def _chat_response_format(output_format: ModelOutputFormat) -> dict[str, Any] | None:
    if output_format.type == "text":
        return None
    if output_format.type == "json_object":
        return {"type": "json_object", **output_format.provider_options}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": output_format.name,
            "strict": output_format.strict,
            "schema": output_format.schema_,
            **output_format.provider_options,
        },
    }


def _provider_error_message(provider: str, exc: httpx.HTTPError) -> str:
    message = f"{provider} provider request failed: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text.strip()
        if body:
            message = f"{message}; response_body={body[:2000]}"
    return message


def responses_text_format(output_format: ModelOutputFormat) -> dict[str, Any] | None:
    if output_format.type == "text":
        return None
    if output_format.type == "json_object":
        return {"text": {"format": {"type": "json_object", **output_format.provider_options}}}
    return {
        "text": {
            "format": {
                "type": "json_schema",
                "name": output_format.name,
                "strict": output_format.strict,
                "schema": output_format.schema_,
                **output_format.provider_options,
            }
        }
    }
