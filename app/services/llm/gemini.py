from app.config import get_settings
from app.http_client import get_http_client
from app.services.llm.base import BaseLLMAdapter, LLMResponse

settings = get_settings()


class GeminiAdapter(BaseLLMAdapter):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured")

        url = f"{self.BASE_URL}/{model}:generateContent"
        client = get_http_client()
        resp = await client.post(
            url,
            params={"key": settings.GEMINI_API_KEY},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(part.get("text", "") for part in parts)
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            model=model,
            backend="gemini",
        )
