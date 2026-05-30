import httpx
from app.services.llm.base import BaseLLMAdapter, LLMResponse
from app.config import get_settings

settings = get_settings()


class OllamaAdapter(BaseLLMAdapter):
    """Calls a local Ollama instance — no API key required."""

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                json={
                    "model": model,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["message"]["content"]
            return LLMResponse(
                text=text,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                model=model,
                backend="ollama",
            )
