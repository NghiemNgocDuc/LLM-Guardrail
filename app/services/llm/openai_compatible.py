import httpx

from app.config import get_settings
from app.services.llm.base import BaseLLMAdapter, LLMResponse

settings = get_settings()


class OpenAICompatibleAdapter(BaseLLMAdapter):
    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        if not settings.OPENAI_COMPATIBLE_BASE_URL:
            raise ValueError("OPENAI_COMPATIBLE_BASE_URL is not configured")
        if not settings.OPENAI_COMPATIBLE_API_KEY:
            raise ValueError("OPENAI_COMPATIBLE_API_KEY is not configured")

        base_url = settings.OPENAI_COMPATIBLE_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_COMPATIBLE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return LLMResponse(
                text=text,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                model=model,
                backend="openai_compatible",
            )
