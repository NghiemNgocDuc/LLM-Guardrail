"""
LLM router — picks the right adapter based on org policy → request override → global default.
"""
from typing import AsyncIterator

from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk
from app.services.llm.anthropic import AnthropicAdapter
from app.services.llm.gemini import GeminiAdapter
from app.services.llm.groq import GroqAdapter
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
    "mock": MockAdapter(),
}

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "groq": "openai/gpt-oss-20b",
    "ollama": "llama3",
    "openai_compatible": "gpt-4o",
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


async def call_llm(
    prompt: str,
    temperature: float,
    max_tokens: int,
    request_backend: str | None = None,
    org_backend: str | None = None,
    request_model: str | None = None,
    org_model: str | None = None,
) -> LLMResponse:
    adapter, backend, model = resolve_adapter(request_backend, org_backend, request_model, org_model)
    return await adapter.complete(prompt, model, temperature, max_tokens)


async def stream_llm(
    prompt: str,
    temperature: float,
    max_tokens: int,
    request_backend: str | None = None,
    org_backend: str | None = None,
    request_model: str | None = None,
    org_model: str | None = None,
) -> AsyncIterator[LLMStreamChunk]:
    """Async generator — yields LLMStreamChunk objects until done=True."""
    adapter, backend, model = resolve_adapter(request_backend, org_backend, request_model, org_model)
    async for chunk in adapter.stream(prompt, model, temperature, max_tokens):
        yield chunk
