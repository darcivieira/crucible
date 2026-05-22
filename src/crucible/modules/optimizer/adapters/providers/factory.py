from __future__ import annotations

from collections.abc import Callable

from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.providers.anthropic import AnthropicAdapter
from crucible.modules.optimizer.adapters.providers.embeddings import (
    FakeEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from crucible.modules.optimizer.adapters.providers.fake import FakeProvider
from crucible.modules.optimizer.adapters.providers.google import GoogleAdapter
from crucible.modules.optimizer.adapters.providers.llamacpp import LlamaCppAdapter
from crucible.modules.optimizer.adapters.providers.ollama import OllamaAdapter
from crucible.modules.optimizer.adapters.providers.openai_compatible import (
    OpenAIAdapter,
    OpenRouterAdapter,
    VLLMAdapter,
)
from crucible.modules.optimizer.adapters.providers.rate_limited import RateLimitedProvider
from crucible.modules.optimizer.domain.models import ModelSpec, ProviderName
from crucible.modules.optimizer.domain.protocols import EmbeddingProvider, ModelProvider


class ModelProviderFactory:
    def __init__(self):
        self._providers: dict[ProviderName, Callable[[ModelSpec], ModelProvider]] = {}
        self._embedding_providers: dict[ProviderName, Callable[[ModelSpec], EmbeddingProvider]] = {}

    def register(
        self, provider: ProviderName, builder: Callable[[ModelSpec], ModelProvider]
    ) -> None:
        self._providers[provider] = builder

    def get(self, spec: ModelSpec) -> ModelProvider:
        try:
            provider = self._providers[spec.provider](spec)
        except KeyError as exc:
            raise ValueError(f"Provider '{spec.provider}' not registered") from exc
        return RateLimitedProvider(provider, spec.rate_limit)

    def register_embedding(
        self, provider: ProviderName, builder: Callable[[ModelSpec], EmbeddingProvider]
    ) -> None:
        self._embedding_providers[provider] = builder

    def get_embedding(self, spec: ModelSpec) -> EmbeddingProvider:
        try:
            return self._embedding_providers[spec.provider](spec)
        except KeyError as exc:
            raise ValueError(f"Embedding provider '{spec.provider}' not registered") from exc


_factory: ModelProviderFactory | None = None


def get_provider_factory() -> ModelProviderFactory:
    global _factory
    if _factory is None:
        settings = get_settings()
        _factory = ModelProviderFactory()
        _factory.register("fake", lambda spec: FakeProvider())
        _factory.register_embedding("fake", lambda spec: FakeEmbeddingProvider())
        _factory.register("ollama", lambda spec: OllamaAdapter(spec, settings.ollama_url))
        _factory.register_embedding(
            "ollama", lambda spec: OllamaEmbeddingProvider(spec, settings.ollama_url)
        )
        _factory.register(
            "openai",
            lambda spec: OpenAIAdapter(spec, "https://api.openai.com", settings.openai_api_key),
        )
        _factory.register_embedding(
            "openai",
            lambda spec: OpenAICompatibleEmbeddingProvider(
                spec, "https://api.openai.com", settings.openai_api_key
            ),
        )
        _factory.register(
            "anthropic",
            lambda spec: AnthropicAdapter(
                spec, "https://api.anthropic.com", settings.anthropic_api_key
            ),
        )
        _factory.register(
            "google",
            lambda spec: GoogleAdapter(
                spec,
                "https://generativelanguage.googleapis.com",
                settings.google_api_key,
            ),
        )
        _factory.register(
            "openrouter",
            lambda spec: OpenRouterAdapter(
                spec,
                "https://openrouter.ai/api",
                settings.openrouter_api_key,
            ),
        )
        _factory.register_embedding(
            "openrouter",
            lambda spec: OpenAICompatibleEmbeddingProvider(
                spec, "https://openrouter.ai/api", settings.openrouter_api_key
            ),
        )
        _factory.register("vllm", lambda spec: VLLMAdapter(spec, settings.vllm_url))
        _factory.register_embedding(
            "vllm", lambda spec: OpenAICompatibleEmbeddingProvider(spec, settings.vllm_url)
        )
        _factory.register("llamacpp", lambda spec: LlamaCppAdapter(spec, settings.llamacpp_url))
    return _factory
