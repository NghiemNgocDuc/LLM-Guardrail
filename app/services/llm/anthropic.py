import httpx
from app.services.llm.base import BaseLLMAdapter, LLMResponse
from app.config import get_settings

settings = get_settings()


class AnthropicAdapter(BaseLLMAdapter):
    BASE_URL = "https://api.anthropic.com/v1/messages"

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.BASE_URL,
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            return LLMResponse(
                text=text,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                model=model,
                backend="anthropic",
            )
