from app.services.llm.base import BaseLLMAdapter, LLMResponse


class MockAdapter(BaseLLMAdapter):
    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        text = (
            "Mock response: the guardrails pipeline accepted this prompt and "
            "returned a local test response without calling an external LLM."
        )
        return LLMResponse(
            text=text,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(text.split())),
            model=model,
            backend="mock",
        )
