from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic

from crucible.modules.optimizer.domain.models import (
    CompletionResult,
    ModelParams,
    ProviderRateLimit,
)
from crucible.modules.optimizer.domain.protocols import ModelProvider


class RateLimitedProvider:
    def __init__(self, provider: ModelProvider, limits: ProviderRateLimit):
        self.provider = provider
        self.limits = limits
        self._semaphore = asyncio.Semaphore(limits.max_concurrent)
        self._requests: deque[float] = deque()

    async def complete(self, prompt: str, params: ModelParams) -> CompletionResult:
        async with self._semaphore:
            await self._wait_for_rpm_slot()
            return await self.provider.complete(prompt, params)

    async def _wait_for_rpm_slot(self) -> None:
        if self.limits.requests_per_minute is None:
            return
        now = monotonic()
        while self._requests and now - self._requests[0] >= 60:
            self._requests.popleft()
        if len(self._requests) >= self.limits.requests_per_minute:
            wait_seconds = 60 - (now - self._requests[0])
            await asyncio.sleep(max(0.0, wait_seconds))
        self._requests.append(monotonic())
