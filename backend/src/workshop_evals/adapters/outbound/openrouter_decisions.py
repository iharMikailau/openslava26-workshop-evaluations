"""OpenRouter Decisions API adapter, isolated from chat completions."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import Any

import httpx
from pydantic import ValidationError

from workshop_evals.domain.decision_catalog import DecisionModel
from workshop_evals.domain.decision_lab import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionError,
    DecisionUsage,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)

URL = "https://openrouter.ai/api/alpha/decisions"


def _distribution(raw: Any, keys: set[str]) -> dict[str, float]:
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ValueError("distribution keys do not match the criterion")
    values = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("invalid probability")
        values[key] = float(value)
    if abs(sum(values.values()) - 1) > 0.001:
        raise ValueError("probabilities do not sum to one")
    return values


def _answer(question: Question, raw: Any) -> NoulAnswer | ChoiceAnswer | ScoreAnswer:
    if not isinstance(raw, dict) or raw.get("type") != question.type:
        raise ValueError("missing or mismatched answer")
    if isinstance(question, NoulQuestion):
        if raw.get("noul") is None:
            raise ValueError("missing Noul probability")
        return NoulAnswer(type="noul", probability=raw["noul"])
    if isinstance(question, ChoiceQuestion):
        probs = _distribution(raw["probabilities"], set(question.criteria))
        winner = raw["choice"]
        if winner not in probs or probs[winner] < max(probs.values()):
            raise ValueError("choice does not match its distribution")
        return ChoiceAnswer(
            type="choice", value=winner, probabilities=probs, confidence=raw.get("confidence")
        )
    assert isinstance(question, ScoreQuestion)
    keys = {str(i) for i in range(len(question.criteria))}
    probabilities = _distribution(raw["probabilities"], keys)
    legend = {str(i): value for i, value in enumerate(question.criteria)}
    if raw.get("legend") != legend:
        raise ValueError("score legend does not match its levels")
    return ScoreAnswer.from_raw(
        raw["score"],
        len(question.criteria),
        probabilities=[probabilities[str(i)] for i in range(len(keys))],
        confidence=raw.get("confidence"),
    )


class OpenRouterDecisionClient:
    def __init__(self, *, timeout: float = 30, max_retries: int = 2) -> None:
        self._timeout = timeout
        self._max_retries = min(max(max_retries, 0), 2)

    async def decide(
        self,
        model: DecisionModel,
        item_id: str,
        state: dict[str, str | None],
        questions: list[Question],
    ) -> Judgment:
        started = time.perf_counter()
        result = Judgment(item_id=item_id, judge_id=model.id, requested_model=model.model_id)
        key = os.environ.get(model.api_key_env, "").strip()
        if not key:
            result.usage.attempts = 0
            result.error = DecisionError(
                code="missing_key",
                message=(
                    "Set OPENROUTER_API_KEY in the backend environment or "
                    "Models → Session credentials."
                ),
            )
            return result
        body = {
            "model": model.model_id,
            "state": state,
            "questions": {q.id: q.model_dump(exclude={"id"}, exclude_none=True) for q in questions},
        }
        data: Any = None
        for attempt in range(1, self._max_retries + 2):
            result.usage.attempts = attempt
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        URL, json=body, headers={"Authorization": f"Bearer {key}"}
                    )
                if (response.status_code == 429 or response.status_code >= 500) and (
                    attempt <= self._max_retries
                ):
                    try:
                        delay = min(max(float(response.headers.get("retry-after", "0")), 0), 2)
                    except ValueError:
                        delay = 0
                    await asyncio.sleep(max(delay, 0.2 * attempt))
                    continue
                if not response.is_success:
                    code = response.status_code
                    result.error = DecisionError(
                        code=f"http_{code}",
                        message=(
                            f"OpenRouter decision request failed (HTTP {code}); check credentials, "
                            "credits, model availability, rate limits, and input size."
                        ),
                    )
                    break
                try:
                    data = response.json()
                except ValueError:
                    result.error = DecisionError(
                        code="invalid_response", message="OpenRouter returned invalid JSON."
                    )
                    break
                if not isinstance(data, dict) or data.get("error"):
                    result.error = DecisionError(
                        code="upstream_error", message="OpenRouter returned an error response."
                    )
                break
            except httpx.TransportError:
                if attempt <= self._max_retries:
                    await asyncio.sleep(0.2 * attempt)
                    continue
                result.error = DecisionError(
                    code="transport_error", message="OpenRouter request failed or timed out."
                )
        result.usage.latency_ms = int((time.perf_counter() - started) * 1000)
        if result.error or not isinstance(data, dict):
            return result
        result.returned_model = data.get("model") if isinstance(data.get("model"), str) else None
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        with contextlib.suppress(ValidationError):
            result.usage = DecisionUsage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                cost_usd=usage.get("cost"),
                latency_ms=result.usage.latency_ms,
                attempts=result.usage.attempts,
            )
        answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
        for question in questions:
            try:
                raw = answers.get(question.id)
                result.answers[question.id] = _answer(question, raw)
                allowed = {
                    "type",
                    "noul",
                    "choice",
                    "score",
                    "probabilities",
                    "legend",
                    "confidence",
                }
                result.raw_answers[question.id] = {k: v for k, v in raw.items() if k in allowed}
            except (KeyError, TypeError, ValueError, ValidationError):
                result.question_errors[question.id] = DecisionError(
                    code="invalid_answer", message="Missing or invalid answer for this question."
                )
        return result
