"""One-request OpenRouter client with explicit consent and usage accounting.

No network calls happen on import or construction. This module intentionally
cannot select tools, browse URLs, buy tickets, or loop through model calls.
"""
from __future__ import annotations
from providers.config import environment_file

import os
import json
import re
from typing import Any, Callable
import requests

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_INPUT_CHARS = 1200
MAX_OUTPUT_TOKENS = 256
SMOKE_OUTPUT_TOKENS = 512
GEMMA_MODEL = "google/gemma-4-26b-a4b-it:free"
NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


class LLMConfigurationError(ValueError):
    """Model/key/permissions configuration problem."""


class LLMCallError(RuntimeError):
    """Network, provider, or response error (no secrets returned)."""


def load_local_env() -> None:
    """Load existing .env when python-dotenv is available; no secrets printed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(environment_file(), override=False)


def _default_transport(body: dict[str, Any], key: str, timeout: float) -> dict[str, Any]:
    try:
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "X-Title": "TravelMind University Prototype"},
            json=body, timeout=(10.0, timeout),
        )
    except requests.exceptions.SSLError as exc:
        reason = "certificate verification failed" if "CERTIFICATE_VERIFY_FAILED" in str(exc) else "handshake/connection interrupted (possibly unexpected EOF)"
        raise LLMCallError(f"OpenRouter SSL/TLS {reason}; check network, certificates or HTTPS proxy; no retry made") from None
    except requests.exceptions.ConnectTimeout:
        raise LLMCallError("OpenRouter connection timed out after 10 seconds; check network/proxy; no retry made") from None
    except requests.exceptions.ReadTimeout:
        raise LLMCallError(f"OpenRouter response timed out after {timeout:g} seconds; no retry made") from None
    except requests.exceptions.ProxyError:
        raise LLMCallError("OpenRouter proxy connection failed; check proxy configuration; no retry made") from None
    except requests.exceptions.ConnectionError:
        raise LLMCallError("OpenRouter connection failed before a response (DNS/TCP or connection reset); check network/proxy; no retry made") from None
    except requests.RequestException as exc:
        # Never print URL with headers, raw request body, or token.
        raise LLMCallError(f"OpenRouter connection failed ({type(exc).__name__}); no retry made") from None
    if not resp.ok:
        descriptions = {
            400: "invalid request or model parameters",
            401: "invalid or expired API key",
            402: "insufficient credits or account limit",
            403: "access to model denied",
            404: "model/endpoint not available",
            429: "rate limit reached (free models are limited)",
        }
        detail = descriptions.get(resp.status_code, "provider/server error")
        if resp.status_code == 429:
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            error = payload.get("error") if isinstance(payload, dict) else None
            metadata = error.get("metadata") if isinstance(error, dict) else None
            metadata = metadata if isinstance(metadata, dict) else {}

            def safe_detail(value):
                if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                    return None
                value = str(value)
                if key:
                    value = value.replace(key, "[REDACTED]")
                value = re.sub(r"(?i)bearer\s+[^\s,;]+|sk-[A-Za-z0-9_-]+", "[REDACTED]", value)
                return " ".join(value.split())[:500]

            rate_limit = {name: safe_detail(metadata.get(name)) for name in
                          ("limit_source", "provider_name", "remedy_hint")}
            rate_limit.update({name: safe_detail(resp.headers.get(name)) for name in
                               ("Retry-After", "X-RateLimit-Reset")})
            detail += "; " + json.dumps(rate_limit, sort_keys=True)
        raise LLMCallError(f"OpenRouter HTTP {resp.status_code}: {detail}; no retry made")
    try:
        result = resp.json()
    except ValueError:
        raise LLMCallError("OpenRouter returned non-JSON; no retry made") from None
    if not isinstance(result, dict):
        raise LLMCallError("OpenRouter response was not a JSON object")
    return result


def _read_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMCallError("OpenRouter returned no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LLMCallError("OpenRouter returned no assistant message")
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
                       and isinstance(part.get("text"), str)).strip()
    else:
        text = ""
    if not text:
        state = ("missing" if "content" not in message else
                 "null" if content is None else
                 "empty" if isinstance(content, (str, list)) else "invalid")
        usage = response.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        details = usage.get("completion_tokens_details")
        details = details if isinstance(details, dict) else {}
        # Only known finish reasons and numeric counts are safe to report.
        reason = choices[0].get("finish_reason")
        reason = reason if isinstance(reason, str) and reason in {
            "stop", "length", "tool_calls", "content_filter", "error", "function_call"
        } else "unknown"
        reasoning_present = any(k in message for k in ("reasoning", "reasoning_details"))
        raise LLMCallError(
            f"Model returned no final text: message.content={state}, "
            f"finish_reason={reason}, "
            f"completion_tokens={_safe_int(usage.get('completion_tokens'))}, "
            f"reasoning_tokens={_safe_int(details.get('reasoning_tokens'))}, "
            f"reasoning_present={reasoning_present}. No retry made."
        )
    return text


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenRouterClient:
    def __init__(self, *, model: str | None = None, api_key: str | None = None,
                 transport: Callable[[dict[str, Any], str, float], dict[str, Any]] | None = None):
        self.model = model
        self.api_key = api_key
        self.transport = transport or _default_transport

    def complete(self, *, system: str, user: str, live: bool = False,
                 allow_paid_model: bool = False, smoke_test: bool = False) -> dict[str, Any]:
        """Use at most one LLM request. No calls without explicit live=True."""
        if not live:
            raise LLMConfigurationError("Live LLM access requires explicit --live-llm")
        if not isinstance(system, str) or not isinstance(user, str):
            raise ValueError("Messages must be strings")
        if not user.strip() or len(system) + len(user) > MAX_INPUT_CHARS:
            raise ValueError(f"Prompt cannot be empty or exceed {MAX_INPUT_CHARS} characters total")
        model = (self.model or os.getenv("OPENROUTER_MODEL", "")).strip()
        key = self.api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        if not model:
            raise LLMConfigurationError("Set OPENROUTER_MODEL to an explicit model ID")
        if not key:
            raise LLMConfigurationError("Set OPENROUTER_API_KEY in your private .env")
        # Only explicitly free model IDs are permitted, including the official router.
        if not (model.endswith(":free") or model == "openrouter/free"):
            raise LLMConfigurationError(
                "Paid/unknown-price model blocked. Choose a :free model or openrouter/free"
            )
        output_limit = (SMOKE_OUTPUT_TOKENS if smoke_test and model != GEMMA_MODEL
                        else MAX_OUTPUT_TOKENS)
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_completion_tokens": output_limit,
            "temperature": 0,
            "stream": False,
            "usage": {"include": True},
        }
        if model == NEMOTRON_MODEL:
            body["reasoning"] = {"effort": "low"}
        elif model == GEMMA_MODEL:
            body["reasoning"] = {"enabled": False}
        # SINGLE transport invocation; never automatically retry or fall back.
        answer = self.transport(body, key, 90.0)
        raw = answer.get("usage") or {}
        if not isinstance(raw, dict):
            raw = {}
        tokens_in = _safe_int(raw.get("prompt_tokens"))
        tokens_out = _safe_int(raw.get("completion_tokens"))
        total = _safe_int(raw.get("total_tokens"))
        cost = raw.get("cost")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool):
            cost = None
        # Whitelist metadata only: never include prompts, headers or reasoning text.
        def safe_model(value):
            return (value if isinstance(value, str) and value != key
                    and key not in value and re.fullmatch(r"[A-Za-z0-9_./:\-]{1,160}", value)
                    else None)
        request_config = {
            "requested_model": safe_model(model),
            "model_source": "explicit" if self.model else "OPENROUTER_MODEL",
            "reasoning": body.get("reasoning"), "temperature": body["temperature"],
            "max_completion_tokens": output_limit, "stop": body.get("stop"),
            "stream": body["stream"], "usage": body["usage"],
        }
        choices = answer.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        finish = choice.get("finish_reason")
        diagnostics = {**request_config, "returned_model": safe_model(answer.get("model")),
                       "finish_reason": finish if isinstance(finish, str) and finish in {
                           "stop", "length", "tool_calls", "content_filter", "error", "function_call"
                       } else None,
                       "completion_tokens": tokens_out,
                       "reasoning_tokens": _safe_int((raw.get("completion_tokens_details")
                           if isinstance(raw.get("completion_tokens_details"), dict) else {}).get("reasoning_tokens")),
                       "final_text_present": False}
        try:
            text = _read_content(answer)
        except LLMCallError as exc:
            raise LLMCallError(f"{exc} Diagnostics: {json.dumps(diagnostics, sort_keys=True)}") from None
        diagnostics["final_text_present"] = True
        return {
            "text": text,
            "model": answer.get("model") or model,
            "usage": {
                "llm_requests_attempted": 1,
                "llm_input_tokens": tokens_in,
                "llm_output_tokens": tokens_out,
                "llm_total_tokens": total,
                "llm_cost_usd_reported": cost,
            },
            "trace": [{"step": "openrouter_chat_completion", "requests_attempted": 1,
                       "max_completion_tokens": output_limit, "automatic_retries": 0,
                       "diagnostics": diagnostics}],
        }
