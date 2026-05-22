import os

import pytest

from crucible import ModelParams, ModelSpec
from crucible.modules.optimizer.adapters.providers.factory import get_provider_factory

pytestmark = pytest.mark.skipif(
    os.getenv("CRUCIBLE_RUN_PROVIDER_SMOKE") != "1",
    reason="set CRUCIBLE_RUN_PROVIDER_SMOKE=1 to run live provider smoke tests",
)


@pytest.mark.asyncio
async def test_live_provider_smoke():
    provider_name = os.getenv("CRUCIBLE_SMOKE_PROVIDER", "ollama")
    model_id = os.getenv("CRUCIBLE_SMOKE_MODEL", "gemma3:4b")
    provider = get_provider_factory().get(
        ModelSpec(provider=provider_name, model_id=model_id, role="target")  # type: ignore[arg-type]
    )

    result = await provider.complete("Responda apenas: ok", ModelParams(max_tokens=8))

    assert result.text.strip()
