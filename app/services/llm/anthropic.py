import json
import httpx
from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk
from app.config import get_settings

settings = get_settings()


class AnthropicAdapter(BaseLLMAdapter):
    BASE_URL = "https://api.anthropic.com/v1/messages"
    _HEADERS_BASE = {"anthropic-version": "2023-06-01", "content-type": "application/json"}

    def _headers(self) -> dict:
        return {**self._HEADERS_BASE, "x-api-key": settings.ANTHROPIC_API_KEY}

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self.BASE_URL,
                headers=self._headers(),
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            return LLMResponse(
                text=data["content"][0]["text"],
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                model=model,
                backend="anthropic",
            )

    async def stream(self, prompt: str, model: str, temperature: float, max_tokens: int):
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", self.BASE_URL,
                headers=self._headers(),
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as resp:
                resp.raise_for_status()
                input_tokens = output_tokens = 0
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("type")
                    if event_type == "message_start":
                        input_tokens = data.get("message", {}).get("usage", {}).get("input_tokens", 0)
                    elif event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            content = delta.get("text", "")
                            if content:
                                yield LLMStreamChunk(token=content, done=False, model=model, backend="anthropic")
                    elif event_type == "message_delta":
                        output_tokens = data.get("usage", {}).get("output_tokens", 0)
                    elif event_type == "message_stop":
                        yield LLMStreamChunk(
                            token="", done=True,
                            input_tokens=input_tokens, output_tokens=output_tokens,
                            model=model, backend="anthropic",
                        )
                        return
