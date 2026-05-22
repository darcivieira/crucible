from typing import Any

from crucible.modules.optimizer.adapters.providers.base_http import (
    HttpProvider,
    responses_text_format,
)
from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class OpenAIAdapter(HttpProvider):
    @property
    def path(self) -> str:
        if self.spec.api_mode == "responses":
            return "/v1/responses"
        return super().path

    def payload(self, prompt: str, params: ModelParams) -> dict[str, Any]:
        if self.spec.api_mode != "responses":
            return super().payload(prompt, params)
        data: dict[str, Any] = {
            "model": self.spec.model_id,
            "input": prompt,
            "temperature": params.temperature,
            "max_output_tokens": params.max_tokens,
        }
        text_format = responses_text_format(self.spec.output_format)
        if text_format is not None:
            data.update(text_format)
        data.update(params.extra)
        return data

    def parse(self, payload: dict[str, Any]) -> CompletionResult:
        if self.spec.api_mode != "responses":
            return super().parse(payload)
        usage = payload.get("usage") or {}
        text = payload.get("output_text")
        if text is None:
            text = _responses_output_text(payload)
        return CompletionResult(
            text=text,
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
            finish_reason=payload.get("status") or "stop",
            raw=payload,
        )


class OpenRouterAdapter(HttpProvider):
    pass


class VLLMAdapter(HttpProvider):
    pass


def _responses_output_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"}:
                chunks.append(str(content.get("text", "")))
    return "".join(chunks)
