from __future__ import annotations

from typing import Protocol

from crucible.modules.optimizer.domain.models import (
    CompletionResult,
    ExecutionResult,
    ModelParams,
    OptimizationRun,
)


class ModelProvider(Protocol):
    async def complete(self, prompt: str, params: ModelParams) -> CompletionResult: ...


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ExecutionCache(Protocol):
    async def get(self, key: str) -> ExecutionResult | None: ...
    async def set(self, key: str, value: ExecutionResult) -> None: ...


class RunStore(Protocol):
    async def save_run(self, run: OptimizationRun) -> None: ...
    async def save_iteration(self, run: OptimizationRun) -> None: ...
    async def load_run(self, run_id: str) -> OptimizationRun: ...
