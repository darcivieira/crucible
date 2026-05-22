import pytest

from crucible import ModelSpec
from crucible.modules.optimizer.adapters.cache import JsonlExecutionCache, execution_cache_key
from crucible.modules.optimizer.adapters.importers import (
    import_dspy,
    import_jsonl,
    import_promptfoo,
)
from crucible.modules.optimizer.adapters.providers.anthropic import AnthropicAdapter
from crucible.modules.optimizer.adapters.providers.factory import ModelProviderFactory
from crucible.modules.optimizer.adapters.providers.google import GoogleAdapter
from crucible.modules.optimizer.adapters.providers.llamacpp import LlamaCppAdapter
from crucible.modules.optimizer.adapters.providers.ollama import OllamaAdapter
from crucible.modules.optimizer.adapters.providers.openai_compatible import OpenAIAdapter
from crucible.modules.optimizer.adapters.providers.rate_limited import RateLimitedProvider
from crucible.modules.optimizer.adapters.storage import FileRunStore, SQLiteRunStore
from crucible.modules.optimizer.domain.models import (
    ExecutionResult,
    OptimizationConfig,
    OptimizationRun,
    Prompt,
)


def _spec(provider="ollama"):
    return ModelSpec(provider=provider, model_id="m", role="target")


@pytest.mark.asyncio
async def test_jsonl_execution_cache_round_trip(tmp_path):
    cache = JsonlExecutionCache(tmp_path / "cache.jsonl")
    prompt = Prompt(template="{input}", variables=["input"])
    key = execution_cache_key(prompt, "hello", _spec())
    execution = ExecutionResult(test_case_id="case", actual_output="ok", latency_ms=1)

    assert await cache.get(key) is None
    await cache.set(key, execution)

    loaded = await cache.get(key)
    assert loaded is not None
    assert loaded.actual_output == "ok"


@pytest.mark.asyncio
async def test_file_run_store_round_trip(tmp_path):
    config = OptimizationConfig(
        target_model=_spec("fake"),
        reasoning_model=ModelSpec(provider="fake", model_id="r", role="reasoning"),
    )
    run = OptimizationRun(config=config, gabarito_hash="g", initial_prompt_hash="p")
    store = FileRunStore(tmp_path)

    await store.save_run(run)
    loaded = await store.load_run(run.id)

    assert loaded.id == run.id
    assert store.list_runs() == [run.id]


@pytest.mark.asyncio
async def test_sqlite_run_store_round_trip_and_latest(tmp_path):
    config = OptimizationConfig(
        target_model=_spec("fake"),
        reasoning_model=ModelSpec(provider="fake", model_id="r", role="reasoning"),
    )
    run = OptimizationRun(config=config, gabarito_hash="g", initial_prompt_hash="p")
    store = SQLiteRunStore(tmp_path / "runs.sqlite")

    await store.save_run(run)

    assert (await store.load_run(run.id)).id == run.id
    assert (await store.load_run("latest")).id == run.id
    summaries = store.list_runs()
    assert summaries[0].id == run.id


def test_model_provider_factory_registers_custom_provider():
    class Provider:
        async def complete(self, prompt, params):
            raise NotImplementedError

    factory = ModelProviderFactory()
    factory.register("fake", lambda spec: Provider())

    assert isinstance(factory.get(_spec("fake")), RateLimitedProvider)
    with pytest.raises(ValueError):
        factory.get(_spec("ollama"))


def test_provider_payload_and_parse_shapes():
    ollama = OllamaAdapter(_spec("ollama"), "http://localhost")
    assert ollama.payload("prompt", _spec().params)["model"] == "m"
    assert ollama.parse({"response": "ok", "eval_count": 2}).text == "ok"

    openai = OpenAIAdapter(_spec("openai"), "http://localhost")
    parsed = openai.parse(
        {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
    )
    assert parsed.tokens_out == 2

    anthropic = AnthropicAdapter(_spec("anthropic"), "http://localhost", "key")
    assert "anthropic-version" in anthropic.headers
    assert anthropic.parse({"content": [{"type": "text", "text": "ok"}]}).text == "ok"

    google = GoogleAdapter(_spec("google"), "http://localhost", "key")
    assert google.path.endswith(":generateContent")
    assert google.parse({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}).text == "ok"

    llamacpp = LlamaCppAdapter(_spec("llamacpp"), "http://localhost")
    assert llamacpp.path == "/completion"
    assert llamacpp.parse({"content": "ok"}).text == "ok"


def test_importers_convert_external_formats():
    jsonl = import_jsonl('{"id": "a", "input": "hello", "expected_output": "world"}')
    promptfoo = import_promptfoo(
        """
tests:
  - vars:
      input: hello
    assert:
      - type: contains
        value: world
"""
    )
    dspy = import_dspy('{"examples": [{"question": "hello", "answer": "world"}]}')
    promptfoo_regex = import_promptfoo(
        """
tests:
  - id: r1
    vars:
      question: invoice
    assert:
      type: regex
      value: '\\d+'
    tags:
      regression: true
"""
    )
    langsmith = import_dspy(
        '{"trainset": [{"inputs": {"query": "q"}, "outputs": {"answer": "a"}}]}'
    )

    assert jsonl.cases[0].id == "a"
    assert promptfoo.cases[0].expected_output == "world"
    assert dspy.cases[0].input == "hello"
    assert promptfoo_regex.cases[0].assertion.type == "regex"
    assert promptfoo_regex.cases[0].tags == ["regression"]
    assert langsmith.cases[0].expected_output == "a"
