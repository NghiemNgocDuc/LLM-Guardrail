import json
from app.http_client import get_http_client
from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk
from app.config import get_settings

settings = get_settings()


class OllamaAdapter(BaseLLMAdapter):
    """Calls a local/remote Ollama instance — no API key required."""

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        client = get_http_client()
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

    async def stream(self, prompt: str, model: str, temperature: float, max_tokens: int):
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        client = get_http_client()
        async with client.stream(
            "POST", url,
            json={
                "model": model,
                "stream": True,
                "options": {"temperature": temperature, "num_predict": max_tokens},
                "messages": [{"role": "user", "content": prompt}],
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if data.get("done"):
                    yield LLMStreamChunk(
                        token="", done=True,
                        input_tokens=data.get("prompt_eval_count", 0),
                        output_tokens=data.get("eval_count", 0),
                        model=model, backend="ollama",
                    )
                else:
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield LLMStreamChunk(token=content, done=False, model=model, backend="ollama")
