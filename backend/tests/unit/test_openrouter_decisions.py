import json

import httpx
import pytest
import respx

from workshop_evals.adapters.outbound.openrouter_decisions import URL, OpenRouterDecisionClient
from workshop_evals.domain.decision_catalog import DECISION_MODELS
from workshop_evals.domain.decision_lab import ChoiceQuestion, NoulQuestion, ScoreQuestion


def questions():
    return [
        NoulQuestion(id="ok", type="noul", instructions="Supported?"),
        ChoiceQuestion(
            id="kind", type="choice", instructions="Which?", criteria={"a": "A", "b": "B"}
        ),
        ScoreQuestion(
            id="quality", type="score", instructions="Quality?", criteria=["Low", "High"]
        ),
    ]


def response():
    return {
        "model": "resolved",
        "usage": {"input_tokens": 12, "cost": 0.01},
        "answers": {
            "ok": {"type": "noul", "noul": 0.8},
            "kind": {
                "type": "choice",
                "choice": "a",
                "probabilities": {"a": 0.8, "b": 0.2},
                "confidence": 0.7,
            },
            "quality": {
                "type": "score",
                "score": 0.25,
                "probabilities": {"0": 0.75, "1": 0.25},
                "legend": {"0": "Low", "1": "High"},
                "confidence": 0.99,
            },
        },
    }


@respx.mock
async def test_request_and_typed_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=response()))
    result = await OpenRouterDecisionClient().decide(
        DECISION_MODELS[0], "item", {"answer": "text"}, questions()
    )
    request = route.calls[0].request
    body = json.loads(request.content)
    assert request.headers["Authorization"] == "Bearer secret"
    assert body["model"] == "typesafe/jev-1.14"
    assert set(body["questions"]) == {"ok", "kind", "quality"}
    assert "labels" not in body["state"] and "temperature" not in body
    assert result.returned_model == "resolved" and result.usage.cost_usd == 0.01
    assert result.answers["quality"].normalized == 0.25
    assert result.answers["quality"].confidence == 0.99
    assert result.answers["ok"].probability == 0.8


@respx.mock
async def test_bad_sibling_isolated_and_missing_metadata(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    data = response()
    data["answers"]["kind"]["choice"] = "b"
    del data["answers"]["quality"]
    del data["usage"]
    respx.post(URL).mock(return_value=httpx.Response(200, json=data))
    result = await OpenRouterDecisionClient().decide(DECISION_MODELS[1], "item", {}, questions())
    assert set(result.answers) == {"ok"}
    assert set(result.question_errors) == {"kind", "quality"}
    assert result.usage.cost_usd is None


@respx.mock
async def test_missing_key_and_bounded_retries(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    route = respx.post(URL).mock(return_value=httpx.Response(429))
    client = OpenRouterDecisionClient()
    result = await client.decide(DECISION_MODELS[0], "item", {}, questions())
    assert result.error.code == "missing_key" and route.call_count == 0
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    result = await client.decide(DECISION_MODELS[0], "item", {}, questions())
    assert result.error.code == "http_429" and route.call_count == 3
    assert result.usage.attempts == 3 and "secret" not in result.model_dump_json()


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 402, 413])
async def test_nontransient_errors_are_not_retried(monkeypatch, status):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    route = respx.post(URL).mock(return_value=httpx.Response(status, text="secret"))
    result = await OpenRouterDecisionClient().decide(DECISION_MODELS[2], "item", {}, questions())
    assert route.call_count == 1
    assert result.error.code == f"http_{status}" and "secret" not in result.model_dump_json()


@respx.mock
@pytest.mark.parametrize("model", DECISION_MODELS)
async def test_each_model_uses_exact_identifier(monkeypatch, model):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=response()))
    await OpenRouterDecisionClient().decide(model, "item", {"prompt": "Q"}, questions())
    assert json.loads(route.calls[0].request.content)["model"] == model.model_id


@respx.mock
@pytest.mark.parametrize("change", ["distribution", "legend", "type", "score", "confidence"])
async def test_invalid_score_does_not_erase_siblings(monkeypatch, change):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    data = response()
    score = data["answers"]["quality"]
    if change == "distribution":
        score["probabilities"]["1"] = 0.5
    elif change == "legend":
        score["legend"]["0"] = "Wrong"
    elif change == "type":
        score["type"] = "choice"
    elif change == "score":
        score["score"] = 3
    else:
        score["confidence"] = float("inf")
    respx.post(URL).mock(return_value=httpx.Response(200, text=json.dumps(data)))
    result = await OpenRouterDecisionClient().decide(DECISION_MODELS[0], "item", {}, questions())
    assert set(result.answers) == {"ok", "kind"}
    assert "quality" in result.question_errors


@respx.mock
async def test_invalid_json_is_not_retried(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    route = respx.post(URL).mock(return_value=httpx.Response(200, text="not JSON"))
    result = await OpenRouterDecisionClient().decide(DECISION_MODELS[0], "item", {}, questions())
    assert route.call_count == 1 and result.error.code == "invalid_response"


@respx.mock
async def test_server_failure_retries_then_preserves_requested_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=response())]
    )
    result = await OpenRouterDecisionClient().decide(DECISION_MODELS[2], "item", {}, questions())
    assert route.call_count == 2 and result.usage.attempts == 2
    assert result.requested_model == "microsoft/microsoft-decision-1"
    assert all(
        json.loads(call.request.content)["model"] == result.requested_model for call in route.calls
    )


@respx.mock
async def test_transport_timeout_is_bounded(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("secret"))
    result = await OpenRouterDecisionClient().decide(DECISION_MODELS[0], "item", {}, questions())
    assert route.call_count == 3 and result.usage.attempts == 3
    assert result.error.code == "transport_error" and "secret" not in result.model_dump_json()
