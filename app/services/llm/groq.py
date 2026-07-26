import json
from app.config import get_settings
from app.http_client import get_http_client
from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk

settings = get_settings()


class GroqAdapter(BaseLLMAdapter):
    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured")

        base_url = settings.GROQ_BASE_URL.rstrip("/")
        client = get_http_client()
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "include_reasoning": False,
                "reasoning_effort": "low",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=model,
            backend="groq",
        )

    async def stream(self, prompt: str, model: str, temperature: float, max_tokens: int):
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured")

        base_url = settings.GROQ_BASE_URL.rstrip("/")
        client = get_http_client()
        async with client.stream(
            "POST", f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            },
        ) as resp:
            resp.raise_for_status()
            input_tokens = output_tokens = 0
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    yield LLMStreamChunk(
                        token="", done=True,
                        input_tokens=input_tokens, output_tokens=output_tokens,
                        model=model, backend="groq",
                    )
                    return
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if data.get("x_groq", {}).get("usage"):
                    usage = data["x_groq"]["usage"]
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("delta", {}).get("content") or ""
                    if content:
                        yield LLMStreamChunk(token=content, done=False, model=model, backend="groq")
