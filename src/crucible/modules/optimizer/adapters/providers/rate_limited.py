from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic
from typing import Any

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

    async def create_context_cache(self, content: str, ttl_seconds: int) -> str:
        provider: Any = self.provider
        async with self._semaphore:
            await self._wait_for_rpm_slot()
            return await provider.create_context_cache(content, ttl_seconds)

    async def complete_with_cached_context(
        self,
        prompt: str,
        params: ModelParams,
        cache_id: str,
    ) -> CompletionResult:
        provider: Any = self.provider
        async with self._semaphore:
            await self._wait_for_rpm_slot()
            return await provider.complete_with_cached_context(prompt, params, cache_id)

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
