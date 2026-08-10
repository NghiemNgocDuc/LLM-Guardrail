"""
LiteLLM adapter — provider routing, per-request provider fallback, and optional
Redis caching, provided by the open-source `litellm` package.

Configure the org policy with llm_backend="litellm" and a model in litellm's
"<provider>/<model>" form, e.g.:

    llm_backend: "litellm"
    llm_model:   "openai/gpt-4o"

Provider API keys are read from the gateway's environment (OPENAI_API_KEY,
ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, ...) the same way the native
adapters work. litellm additionally reads its own env-based auth (e.g.
AZURE_API_KEY) when a key is not mapped below.

`litellm` is an optional dependency — this module imports it lazily and raises
a clear error when it is missing.
"""
from __future__ import annotations

import os
from typing import Any, AsyncIterator

from app.config import get_settings
from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk

settings = get_settings()

try:  # optional dependency — the rest of the gateway works without it
    import litellm
except ImportError:  # pragma: no cover
    litellm = None

_BACKEND = "litellm"

# provider prefix (as used in "provider/model") -> settings attribute holding the key
_API_KEY_ATTR = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}


def _api_key_for(model: str) -> str | None:
    provider = model.split("/", 1)[0].lower()
    attr = _API_KEY_ATTR.get(provider)
    if not attr:
        return None
    return getattr(settings, attr, "") or None


class LitellmAdapter(BaseLLMAdapter):
    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        fallbacks: list[str] | None = None,
        cache: bool = False,
    ) -> LLMResponse:
        if litellm is None:
            raise RuntimeError(
                "litellm backend requested but 'litellm' is not installed — run: pip install litellm"
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": _api_key_for(model),
        }
        if fallbacks:
            kwargs["fallbacks"] = fallbacks
        if cache:
            kwargs["cache"] = {"type": "redis", "ttl": 6 * 3600}

        resp = await litellm.acompletion(**kwargs)
        if not resp or not resp.choices:
            raise RuntimeError(f"litellm returned an empty response for {model}")
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=getattr(resp, "model", model) or model,
            backend=_BACKEND,
        )

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        fallbacks: list[str] | None = None,
        cache: bool = False,
    ) -> AsyncIterator[LLMStreamChunk]:
        if litellm is None:
            raise RuntimeError(
                "litellm backend requested but 'litellm' is not installed — run: pip install litellm"
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "api_key": _api_key_for(model),
        }
        if fallbacks:
            kwargs["fallbacks"] = fallbacks
        if cache:
            kwargs["cache"] = {"type": "redis", "ttl": 6 * 3600}

        stream = await litellm.acompletion(**kwargs)
        input_tokens = output_tokens = 0
        resp_model = model
        async for part in stream:
            if part is None:
                continue
            choices = getattr(part, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            usage = getattr(part, "usage", None)
            if usage is not None:
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
            if getattr(choices[0], "finish_reason", None) is not None or (
                content is None and input_tokens
            ):
                continue
            if content:
                yield LLMStreamChunk(token=content, model=resp_model, backend=_BACKEND)
        yield LLMStreamChunk(
            token="", done=True,
            input_tokens=input_tokens, output_tokens=output_tokens,
            model=resp_model, backend=_BACKEND,
        )