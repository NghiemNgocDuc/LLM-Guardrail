import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


@dataclass
class GuardrailClient:
    base_url: str
    api_key: str
    timeout: float = 30.0
    with_retry: bool = False
    max_retries: int = 3

    def _payload(
        self,
        prompt: str,
        model: str | None,
        backend: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if model:
            payload["model"] = model
        if backend:
            payload["backend"] = backend
        return payload

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return min(2.0 ** (attempt - 1), 8.0)

    def chat(
        self,
        prompt: str,
        *,
        model: str | None = None,
        backend: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/chat"
        payload = self._payload(prompt, model, backend, temperature, max_tokens)
        max_retries = self.max_retries if self.with_retry else 0

        for attempt in range(1, max_retries + 2):
            response = httpx.post(
                url,
                headers={"X-Api-Key": self.api_key},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code in (402, 429) and attempt <= max_retries:
                time.sleep(self._retry_delay(response, attempt))
                continue
            response.raise_for_status()
            return response.json()

    async def chat_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        backend: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        SSE stream from /chat/stream.

        Yields parsed events — each is a dict with a "type" field:
          {"type":"token",  "content":"..."}
          {"type":"done",   "status":..., "model":..., ...}
          {"type":"blocked","status":"input_blocked"|"output_blocked", ...}
          {"type":"error",  "detail":"..."}
        Retries only happen before the stream starts: once the first chunk
        arrives the connection is never retried.
        """
        url = self.base_url.rstrip("/") + "/chat/stream"
        payload = self._payload(prompt, model, backend, temperature, max_tokens)
        max_retries = self.max_retries if self.with_retry else 0
        attempt = 0

        while True:
            attempt += 1
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={"X-Api-Key": self.api_key},
                    json=payload,
                ) as response:
                    if response.status_code in (402, 429) and attempt <= max_retries:
                        await asyncio.sleep(self._retry_delay(response, attempt))
                        continue
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            yield json.loads(line[len("data: "):])
                    return