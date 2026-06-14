"""
Abstract LLM adapter — every backend implements this interface.
Swap providers by changing a single config value.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    backend: str


@dataclass
class LLMStreamChunk:
    token: str
    done: bool = False
    input_tokens: int = 0   # populated only on the final done=True chunk
    output_tokens: int = 0  # populated only on the final done=True chunk
    model: str = ""
    backend: str = ""


class BaseLLMAdapter(ABC):
    """All LLM backends implement this contract."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        ...

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[LLMStreamChunk]:
        """
        Yield LLMStreamChunk objects token by token.
        The final chunk has done=True and carries total token counts.

        Default implementation falls back to complete() and yields the full
        response as a single chunk — backends override this for real streaming.
        """
        resp = await self.complete(prompt, model, temperature, max_tokens)
        yield LLMStreamChunk(token=resp.text, done=False, model=resp.model, backend=resp.backend)
        yield LLMStreamChunk(
            token="", done=True,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            model=resp.model,
            backend=resp.backend,
        )
