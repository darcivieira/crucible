import pytest

from crucible import ModelOutputFormat, ModelSpec
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
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": 6},
            },
        }
    )
    assert parsed.tokens_out == 2
    assert parsed.cached_tokens_in == 6

    anthropic = AnthropicAdapter(_spec("anthropic"), "http://localhost", "key")
    assert "anthropic-version" in anthropic.headers
    assert anthropic.parse({"content": [{"type": "text", "text": "ok"}]}).text == "ok"

    google = GoogleAdapter(_spec("google"), "http://localhost", "key")
    assert google.path.endswith(":generateContent")
    parsed_google = google.parse(
        {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"cachedContentTokenCount": 3},
        }
    )
    assert parsed_google.text == "ok"
    assert parsed_google.cached_tokens_in == 3

    llamacpp = LlamaCppAdapter(_spec("llamacpp"), "http://localhost")
    assert llamacpp.path == "/completion"
    assert llamacpp.parse({"content": "ok"}).text == "ok"


def test_openai_chat_uses_max_completion_tokens_for_reasoning_models():
    spec = ModelSpec(provider="openai", model_id="gpt-5.4", role="reasoning")
    openai = OpenAIAdapter(spec, "http://localhost")

    payload = openai.payload("prompt", spec.params)

    assert "max_tokens" not in payload
    assert payload["max_completion_tokens"] == spec.params.max_tokens


def test_provider_payloads_include_structured_output_format():
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }
    output_format = ModelOutputFormat(
        type="json_schema",
        name="summary_output",
        strict=True,
        schema=schema,
    )

    openai_chat = OpenAIAdapter(
        _spec("openai").model_copy(update={"output_format": output_format}),
        "http://localhost",
    )
    assert openai_chat.payload("prompt", _spec().params)["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "summary_output",
            "strict": True,
            "schema": schema,
        },
    }

    openai_responses = OpenAIAdapter(
        _spec("openai").model_copy(
            update={"api_mode": "responses", "output_format": output_format}
        ),
        "http://localhost",
    )
    responses_payload = openai_responses.payload("prompt", _spec().params)
    assert openai_responses.path == "/v1/responses"
    assert responses_payload["text"]["format"] == {
        "type": "json_schema",
        "name": "summary_output",
        "strict": True,
        "schema": schema,
    }
    assert (
        openai_responses.parse(
            {
                "output": [
                    {"content": [{"type": "output_text", "text": '{"summary":"ok"}'}]}
                ],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            }
        ).text
        == '{"summary":"ok"}'
    )

    ollama = OllamaAdapter(
        _spec("ollama").model_copy(update={"output_format": output_format}),
        "http://localhost",
    )
    assert ollama.payload("prompt", _spec().params)["format"] == schema


def test_cache_key_includes_output_format():
    prompt = Prompt(template="{input}", variables=["input"])
    plain = _spec("openai")
    structured = plain.model_copy(
        update={
            "output_format": ModelOutputFormat(
                type="json_schema",
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )
        }
    )

    assert execution_cache_key(prompt, "input", plain) != execution_cache_key(
        prompt, "input", structured
    )


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
