import asyncio
from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk


class MockAdapter(BaseLLMAdapter):
    _TEXT = (
        "Mock response: the guardrails pipeline accepted this prompt and "
        "returned a local test response without calling an external LLM."
    )

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        return LLMResponse(
            text=self._TEXT,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(self._TEXT.split())),
            model=model,
            backend="mock",
        )

    async def stream(self, prompt: str, model: str, temperature: float, max_tokens: int):
        words = self._TEXT.split()
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            yield LLMStreamChunk(token=token, done=False, model=model, backend="mock")
            await asyncio.sleep(0.04)
        yield LLMStreamChunk(
            token="", done=True,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=len(words),
            model=model, backend="mock",
        )
