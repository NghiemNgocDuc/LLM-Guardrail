"""
Abstract LLM adapter — every backend implements this interface.
Swap providers by changing a single config value.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    backend: str


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
