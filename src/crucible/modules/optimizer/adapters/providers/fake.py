from __future__ import annotations

from collections.abc import Callable

from crucible.modules.optimizer.domain.models import CompletionResult, ModelParams


class FakeProvider:
    def __init__(self, responder: Callable[[str], str] | None = None):
        self.responder = responder or (lambda prompt: prompt)
        self.prompts: list[str] = []

    async def complete(self, prompt: str, params: ModelParams) -> CompletionResult:
        self.prompts.append(prompt)
        text = self.responder(prompt)
        return CompletionResult(
            text=text, tokens_in=len(prompt.split()), tokens_out=len(text.split())
        )
