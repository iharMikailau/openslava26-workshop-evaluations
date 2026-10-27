"""Unit tests for OpenAICompatClient — httpx calls mocked with respx."""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from workshop_evals.adapters.outbound.openai_compat_client import OpenAICompatClient
from workshop_evals.domain.models import ModelSpec, Provider, RunParams


def _model(
    base_url: str = "http://localhost:11434/v1", *, api_key_env: str | None = None
) -> ModelSpec:
    return ModelSpec(
        id="ollama-llama3",
        display_name="Llama 3 (Ollama)",
        provider=Provider.OPENAI_COMPAT,
        model_id="llama3",
        base_url=base_url,
        api_key_env=api_key_env,
    )


def _params(**kw) -> RunParams:
    return RunParams(**kw)


def _chat_response(content: str = "hello", prompt: int = 10, compl: int = 5) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": compl,
            "total_tokens": prompt + compl,
        },
    }


@respx.mock
async def test_successful_chat_returns_text_and_usage() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response("world", prompt=10, compl=5))
    )

    client = OpenAICompatClient()
    result = await client.chat(_model(), [{"role": "user", "content": "hi"}], _params())

    assert result.text == "world"
    assert result.error is None
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15
    assert result.usage.latency_ms >= 0


@respx.mock
async def test_model_id_propagated() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response())
    )
    result = await OpenAICompatClient().chat(
        _model(), [{"role": "user", "content": "test"}], _params()
    )
    assert result.model_id == "llama3"


@respx.mock
async def test_optional_params_included_when_set() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response())
    )

    await OpenAICompatClient().chat(
        _model(),
        [{"role": "user", "content": "test"}],
        _params(top_p=0.9, seed=42, stop=["END"], presence_penalty=0.1, frequency_penalty=0.2),
    )

    body = json.loads(route.calls[0].request.content)
    assert body["top_p"] == pytest.approx(0.9)
    assert body["seed"] == 42
    assert body["stop"] == ["END"]
    assert body["presence_penalty"] == pytest.approx(0.1)
    assert body["frequency_penalty"] == pytest.approx(0.2)


@respx.mock
async def test_optional_params_omitted_when_none() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response())
    )

    await OpenAICompatClient().chat(
        _model(),
        [{"role": "user", "content": "test"}],
        _params(),  # all optional fields default to None
    )

    body = json.loads(route.calls[0].request.content)
    for optional in ("top_p", "seed", "stop", "presence_penalty", "frequency_penalty"):
        assert optional not in body, f"unexpected key {optional!r} in request body"


@respx.mock
async def test_4xx_error_returned_immediately() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(400, text="bad request")
    )

    result = await OpenAICompatClient(max_retries=2).chat(
        _model(), [{"role": "user", "content": "x"}], _params()
    )

    assert result.text == ""
    assert result.error is not None
    assert "400" in result.error


@respx.mock
async def test_5xx_returns_error() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(503, text="service unavailable")
    )

    # max_retries=0 means a single attempt — no sleep, test stays instant.
    result = await OpenAICompatClient(max_retries=0).chat(
        _model(), [{"role": "user", "content": "x"}], _params()
    )

    assert result.text == ""
    assert result.error is not None
    assert "503" in result.error


async def test_missing_base_url_returns_error_without_network() -> None:
    no_url_model = ModelSpec(
        id="no-url",
        display_name="No URL",
        provider=Provider.OPENAI_COMPAT,
        model_id="test",
        base_url=None,
    )
    result = await OpenAICompatClient().chat(
        no_url_model, [{"role": "user", "content": "hi"}], _params()
    )
    assert result.text == ""
    assert result.error is not None


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, "invalid_api_key", "valid"),
        (402, "insufficient_credits", "credits"),
        (404, "model_not_found", "available"),
        (429, "rate_limit", "rate limit"),
        (502, "upstream_error", "upstream failure"),
    ],
)
@respx.mock
async def test_structured_provider_errors_are_actionable(status, code, expected, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-error-key")
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            status,
            json={"error": {"code": code, "message": "provider failure"}},
        )
    )
    model = _model("https://openrouter.ai/api/v1", api_key_env="OPENROUTER_API_KEY")
    result = await OpenAICompatClient(max_retries=0).chat(
        model, [{"role": "user", "content": "hello"}], _params()
    )
    assert result.error is not None
    assert expected in result.error.lower()


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"code": "model_unavailable", "message": "temporarily unavailable"}},
        {"choices": []},
        {"choices": "malformed"},
        {"choices": [{"message": {"content": 7}}]},
        {"choices": [{"error": {"message": "upstream provider failed"}}]},
    ],
)
@respx.mock
async def test_success_status_with_error_or_unusable_choice_fails(body):
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(200, json=body)
    )
    result = await OpenAICompatClient(max_retries=0).chat(
        _model(), [{"role": "user", "content": "hello"}], _params()
    )
    assert result.error is not None


@respx.mock
async def test_valid_empty_content_remains_a_success():
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": ""}}]})
    )
    result = await OpenAICompatClient(max_retries=0).chat(
        _model(), [{"role": "user", "content": "hello"}], _params()
    )
    assert result.error is None
    assert result.text == ""


@respx.mock
async def test_blank_required_key_fails_before_network(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "  ")
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response())
    )
    model = _model("https://openrouter.ai/api/v1", api_key_env="OPENROUTER_API_KEY")
    result = await OpenAICompatClient(max_retries=0).chat(
        model, [{"role": "user", "content": "hello"}], _params()
    )
    assert result.error and "OPENROUTER_API_KEY" in result.error
    assert route.call_count == 0


@respx.mock
async def test_error_redacts_shared_secret(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-value")
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            401,
            json={"error": {"message": "bad key secret-test-value"}},
        )
    )
    model = _model("https://openrouter.ai/api/v1", api_key_env="OPENROUTER_API_KEY")
    result = await OpenAICompatClient(max_retries=0).chat(
        model, [{"role": "user", "content": "hello"}], _params()
    )
    assert result.error is not None
    assert "secret-test-value" not in result.error


@respx.mock
async def test_openrouter_request_uses_explicit_id_shared_bearer_and_parameters(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-shared-key")
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response("final answer", 11, 7))
    )
    model = ModelSpec(
        id="openrouter-test",
        display_name="Test (OpenRouter)",
        provider=Provider.OPENAI_COMPAT,
        model_id="deepseek/deepseek-v4.1-flash-1017",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        supports_reasoning=True,
    )
    messages = [{"role": "user", "content": "prompt"}]
    result = await OpenAICompatClient(max_retries=0).chat(
        model, messages, _params(temperature=0.3, max_tokens=222, reasoning_effort="high")
    )

    request = route.calls[0].request
    body = json.loads(request.content)
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-shared-key"
    assert body["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert body["messages"] == messages
    assert body["temperature"] == pytest.approx(0.3)
    assert body["max_tokens"] == 222
    assert body["reasoning_effort"] == "high"
    assert result.text == "final answer"
    assert result.usage.total_tokens == 18


@respx.mock
async def test_all_curated_openrouter_ids_use_the_shared_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "shared-key")
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(200, json=_chat_response())
    )
    model_ids = [
        "openai/gpt-6.1-sol",
        "openai/gpt-6.1-terra",
        "openai/gpt-6-luna",
        "anthropic/claude-sonnet-5.5",
        "anthropic/claude-haiku-5.5",
        "anthropic/claude-opus-5.5",
        "deepseek/deepseek-v4.1-flash-1017",
        "qwen/qwen3.8-max-0902",
    ]
    client = OpenAICompatClient(max_retries=0)
    for index, model_id in enumerate(model_ids):
        model = ModelSpec(
            id=f"openrouter-{index}",
            display_name=model_id,
            provider=Provider.OPENAI_COMPAT,
            model_id=model_id,
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        )
        result = await client.chat(model, [{"role": "user", "content": "prompt"}], _params())
        assert result.error is None

    assert [json.loads(call.request.content)["model"] for call in route.calls] == model_ids
    assert {call.request.headers["Authorization"] for call in route.calls} == {"Bearer shared-key"}


@respx.mock
async def test_5xx_retry_count_is_bounded(monkeypatch):
    import workshop_evals.adapters.outbound.openai_compat_client as adapter

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(adapter.asyncio, "sleep", no_sleep)
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=Response(503, json={"error": {"message": "temporary upstream issue"}})
    )
    result = await OpenAICompatClient(max_retries=2).chat(
        _model(), [{"role": "user", "content": "hello"}], _params()
    )
    assert route.call_count == 3
    assert result.error is not None
