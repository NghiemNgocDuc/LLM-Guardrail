"""
LLM router — picks the right adapter based on org policy → request override → global default.
"""
from typing import AsyncIterator

from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk
from app.services.llm.anthropic import AnthropicAdapter
from app.services.llm.circuit_breaker import (
    breaker_before,
    breaker_failure,
    breaker_success,
    get_breaker,
    is_failure,
)
from app.services.llm.gemini import GeminiAdapter
from app.services.llm.groq import GroqAdapter
from app.services.llm.litellm import LitellmAdapter
from app.services.llm.openai import OpenAIAdapter
from app.services.llm.openai_compatible import OpenAICompatibleAdapter
from app.services.llm.ollama import OllamaAdapter
from app.services.llm.mock import MockAdapter
from app.config import get_settings

settings = get_settings()

_ADAPTERS: dict[str, BaseLLMAdapter] = {
    "anthropic": AnthropicAdapter(),
    "openai": OpenAIAdapter(),
    "gemini": GeminiAdapter(),
    "groq": GroqAdapter(),
    "ollama": OllamaAdapter(),
    "openai_compatible": OpenAICompatibleAdapter(),
    "litellm": LitellmAdapter(),
    "mock": MockAdapter(),
}

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "groq": "openai/gpt-oss-20b",
    "ollama": "llama3",
    "openai_compatible": "gpt-4o",
    # litellm models carry a provider prefix, e.g. "openai/gpt-4o"
    "litellm": "openai/gpt-4o",
    "mock": "mock-local",
}


def resolve_adapter(
    request_backend: str | None,
    org_backend: str | None,
    request_model: str | None,
    org_model: str | None,
) -> tuple[BaseLLMAdapter, str, str]:
    """
    Returns (adapter, backend_name, model_name).
    Priority: request override → org policy → global default.
    """
    backend = request_backend or org_backend or settings.DEFAULT_LLM_BACKEND
    model   = request_model   or org_model   or _DEFAULT_MODELS.get(backend, settings.DEFAULT_MODEL)

    adapter = _ADAPTERS.get(backend)
    if not adapter:
        raise ValueError(f"Unknown LLM backend: '{backend}'. Valid options: {list(_ADAPTERS)}")

    return adapter, backend, model


def _candidate_chain(backend: str, model: str, fallbacks: list[str] | None) -> list[tuple[str, str]]:
    """Build the ordered (backend, model) failover chain.

    Primary first, then per-org policy fallbacks ("backend" or
    "backend/model" entries), then the gateway-level LLM_FAILOVER_BACKENDS
    list. Duplicate backends are skipped.
    """
    chain: list[tuple[str, str]] = [(backend, model)]
    existing = {backend}
    for entry in fallbacks or []:
        cand_backend, _, cand_model = entry.partition("/")
        cand_backend = cand_backend.strip()
        if not cand_backend or cand_backend in existing or cand_backend not in _ADAPTERS:
            continue
        cand_model = cand_model.strip() or _DEFAULT_MODELS.get(cand_backend, settings.DEFAULT_MODEL)
        chain.append((cand_backend, cand_model))
        existing.add(cand_backend)
    for cand_backend in (settings.LLM_FAILOVER_BACKENDS or "").split(","):
        cand_backend = cand_backend.strip()
        if not cand_backend or cand_backend in existing or cand_backend not in _ADAPTERS:
            continue
        chain.append((cand_backend, _DEFAULT_MODELS.get(cand_backend, settings.DEFAULT_MODEL)))
        existing.add(cand_backend)
    return chain


async def call_llm(
    prompt: str,
    temperature: float,
    max_tokens: int,
    request_backend: str | None = None,
    org_backend: str | None = None,
    request_model: str | None = None,
    org_model: str | None = None,
    fallbacks: list[str] | None = None,
    cache: bool = False,
) -> LLMResponse:
    """Resolve the backend, then call it with generic per-request failover.

    ``fallbacks`` (list of "backend" or "backend/model" strings) come from
    org policy; the gateway-level LLM_FAILOVER_BACKENDS setting is appended
    after them. Each candidate goes through the circuit breaker; on a
    breaker-worthy failure the next candidate is tried. The litellm adapter
    additionally receives the remaining chain as its own provider fallbacks.
    """
    adapter, backend, model = resolve_adapter(request_backend, org_backend, request_model, org_model)
    chain = _candidate_chain(backend, model, fallbacks)
    last_exc: Exception | None = None
    for idx, (cand_backend, cand_model) in enumerate(chain):
        cand_adapter = _ADAPTERS[cand_backend]
        remaining = [f"{b}/{m}" for b, m in chain[idx + 1:]]
        breaker_before(cand_backend)
        try:
            if isinstance(cand_adapter, LitellmAdapter):
                resp = await cand_adapter.complete(
                    prompt, cand_model, temperature, max_tokens,
                    fallbacks=remaining or None, cache=cache,
                )
            else:
                resp = await cand_adapter.complete(prompt, cand_model, temperature, max_tokens)
        except Exception as exc:
            if is_failure(exc):
                breaker_failure(cand_backend)
            else:
                raise  # config/auth errors are not failover-able
            last_exc = exc
            continue
        breaker_success(cand_backend)
        return resp
    raise last_exc  # every candidate failed — surface the final error


async def stream_llm(
    prompt: str,
    temperature: float,
    max_tokens: int,
    request_backend: str | None = None,
    org_backend: str | None = None,
    request_model: str | None = None,
    org_model: str | None = None,
    fallbacks: list[str] | None = None,
    cache: bool = False,
) -> AsyncIterator[LLMStreamChunk]:
    """Async generator — yields LLMStreamChunk objects until done=True.

    Failover only happens BEFORE the first chunk is yielded (a mid-stream
    provider failure cannot be retried without duplicating tokens already
    sent). Mid-stream failures trip the breaker and propagate to the caller.
    """
    adapter, backend, model = resolve_adapter(request_backend, org_backend, request_model, org_model)
    chain = _candidate_chain(backend, model, fallbacks)
    last_exc: Exception | None = None
    for idx, (cand_backend, cand_model) in enumerate(chain):
        cand_adapter = _ADAPTERS[cand_backend]
        remaining = [f"{b}/{m}" for b, m in chain[idx + 1:]]
        breaker_before(cand_backend)
        started = False
        try:
            if isinstance(cand_adapter, LitellmAdapter):
                stream = cand_adapter.stream(prompt, cand_model, temperature, max_tokens, fallbacks=remaining or None, cache=cache)
            else:
                stream = cand_adapter.stream(prompt, cand_model, temperature, max_tokens)
            async for chunk in stream:
                started = True
                yield chunk
            breaker_success(cand_backend)
            return
        except Exception as exc:
            if is_failure(exc) and not started:
                breaker_failure(cand_backend)
                last_exc = exc
                continue
            if is_failure(exc):
                breaker_failure(cand_backend)
            raise
    raise last_exc  # every candidate failed before producing tokens


def reset_breaker(backend: str) -> None:
    """Force a backend's breaker closed (admin/dev tooling)."""
    get_breaker(backend).reset()
