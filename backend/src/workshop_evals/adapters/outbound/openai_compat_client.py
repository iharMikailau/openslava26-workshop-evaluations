"""OpenAI-compatible chat completion adapter.

Works with any server that speaks POST /chat/completions — Ollama, llama.cpp,
MLX Server, LM Studio, OpenAI, and Azure OpenAI.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import httpx

from workshop_evals.application.ports.llm_client import Message
from workshop_evals.domain.models import Completion, ModelSpec, RunParams, Usage


class OpenAICompatClient:
    """LLM client for any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, *, timeout: float = 180.0, max_retries: int = 2) -> None:
        self._timeout = timeout
        self._max_retries = max_retries

    async def chat(
        self,
        model: ModelSpec,
        messages: list[Message],
        params: RunParams,
    ) -> Completion:
        if not model.base_url:
            return Completion(text="", error="base_url not configured for this model")

        api_key = os.environ.get(model.api_key_env, "").strip() if model.api_key_env else ""
        if model.api_key_env and not api_key:
            return Completion(
                text="",
                error=(
                    f"Missing required {model.api_key_env}. Set it in the backend environment, "
                    "the backend launch-directory .env file, or Models → Session credentials."
                ),
            )

        url = f"{model.base_url.rstrip('/')}/chat/completions"

        body: dict[str, Any] = {
            "model": model.model_id,
            "messages": messages,
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.top_p is not None:
            body["top_p"] = params.top_p
        if params.seed is not None:
            body["seed"] = params.seed
        if params.stop is not None:
            body["stop"] = params.stop
        if params.presence_penalty is not None:
            body["presence_penalty"] = params.presence_penalty
        if params.frequency_penalty is not None:
            body["frequency_penalty"] = params.frequency_penalty
        if model.supports_reasoning and params.reasoning_effort:
            body["reasoning_effort"] = params.reasoning_effort

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        last_error = ""
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                await asyncio.sleep(1.5 * attempt)
            try:
                t0 = time.perf_counter()
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=body, headers=headers)
                latency_ms = int((time.perf_counter() - t0) * 1000)

                data = _response_json(resp)
                upstream_error = _upstream_error(data)
                if resp.status_code >= 500:
                    last_error = _format_error(
                        resp.status_code, upstream_error, api_key, _provider_label(model)
                    )
                    continue  # transient — retry

                if not resp.is_success:
                    return Completion(
                        text="",
                        error=_format_error(
                            resp.status_code, upstream_error, api_key, _provider_label(model)
                        ),
                    )

                if upstream_error:
                    return Completion(
                        text="",
                        error=_format_error(
                            resp.status_code, upstream_error, api_key, _provider_label(model)
                        ),
                    )
                choices = data.get("choices") if isinstance(data, dict) else None
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    return Completion(
                        text="",
                        error="Upstream response did not contain a usable completion choice.",
                    )
                choice = choices[0]
                if choice.get("error"):
                    return Completion(
                        text="",
                        error=_format_error(
                            resp.status_code, choice["error"], api_key, _provider_label(model)
                        ),
                    )
                message = choice.get("message")
                if not isinstance(message, dict) or not isinstance(
                    message.get("content"), (str, type(None))
                ):
                    return Completion(
                        text="", error="Upstream response did not contain usable completion text."
                    )
                text = message.get("content") or ""
                raw = data.get("usage") or {}
                prompt_tokens = raw.get("prompt_tokens", 0)
                completion_tokens = raw.get("completion_tokens", 0)
                total_tokens = raw.get("total_tokens", prompt_tokens + completion_tokens)
                usage = Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                )
                return Completion(text=text, usage=usage, model_id=model.model_id)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            except Exception as exc:
                # Unexpected error — no point retrying
                error = f"{type(exc).__name__}: {_sanitize(str(exc), api_key)}"
                return Completion(text="", error=error)

        return Completion(text="", error=last_error)


def _response_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError):
        return None


def _upstream_error(data: Any) -> Any | None:
    if isinstance(data, dict):
        error = data.get("error")
        if error:
            return error
    return None


def _format_error(status: int, error: Any, secret: str, provider: str) -> str:
    message = ""
    code = ""
    if isinstance(error, dict):
        message = str(error.get("message") or error.get("reason") or "")
        code = str(error.get("code") or "")
    elif error:
        message = str(error)

    lowered = f"{status} {code} {message}".lower()
    if status in {401, 403} or "auth" in lowered or "api key" in lowered:
        guidance = (
            "Check that OPENROUTER_API_KEY is valid."
            if provider == "OpenRouter"
            else "Check the configured provider credential."
        )
    elif status == 402 or "credit" in lowered or "payment" in lowered:
        guidance = (
            "Add credits to your OpenRouter account."
            if provider == "OpenRouter"
            else "Check your account balance and billing status with the configured provider."
        )
    elif status == 404 or (
        "model" in lowered and ("unavailable" in lowered or "not found" in lowered)
    ):
        guidance = (
            "Check that this model is available to your OpenRouter account."
            if provider == "OpenRouter"
            else "Check that this model is available at the configured endpoint."
        )
    elif status == 429 or "rate limit" in lowered:
        guidance = (
            "Wait and retry after the OpenRouter rate limit resets."
            if provider == "OpenRouter"
            else "Wait and retry after the configured provider's rate limit resets."
        )
    elif status >= 500:
        guidance = (
            "OpenRouter reported an upstream failure; retry later."
            if provider == "OpenRouter"
            else "The configured provider reported an upstream failure; retry later."
        )
    else:
        guidance = (
            "Check the model request and OpenRouter status."
            if provider == "OpenRouter"
            else "Check the model request and configured provider status."
        )

    details = _sanitize(message or code or "request rejected", secret)
    details = re.sub(r"[\r\n\t]+", " ", details)[:240]
    return f"{provider} HTTP {status}: {details}. {guidance}"


def _provider_label(model: ModelSpec) -> str:
    if model.base_url and "openrouter.ai" in model.base_url:
        return "OpenRouter"
    return "Upstream provider"


def _sanitize(value: str, secret: str) -> str:
    if secret:
        value = value.replace(secret, "[redacted]")
    return value
