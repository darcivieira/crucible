from __future__ import annotations

import hashlib
import math
from typing import Any

import httpx

from crucible.core.exceptions import ProviderError
from crucible.modules.optimizer.domain.models import ModelSpec


class FakeEmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embedding(text) for text in texts]


class OpenAICompatibleEmbeddingProvider:
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post(
                    "/v1/embeddings",
                    headers=headers,
                    json={"model": self.spec.model_id, "input": texts, **self.spec.params.extra},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.spec.provider} embedding request failed: {exc}") from exc
        payload = response.json()
        return [item["embedding"] for item in sorted(payload.get("data", []), key=_embedding_index)]


class OllamaEmbeddingProvider:
    def __init__(self, spec: ModelSpec, base_url: str, timeout: float = 300.0):
        self.spec = spec
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                for text in texts:
                    response = await client.post(
                        "/api/embeddings",
                        json={"model": self.spec.model_id, "prompt": text},
                    )
                    response.raise_for_status()
                    vectors.append(response.json()["embedding"])
        except httpx.HTTPError as exc:
            raise ProviderError("ollama embedding request failed") from exc
        return vectors


def _embedding_index(item: dict[str, Any]) -> int:
    return int(item.get("index", 0))


def _hash_embedding(text: str, dimensions: int = 32) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    values = [((digest[index % len(digest)] / 255.0) * 2) - 1 for index in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
