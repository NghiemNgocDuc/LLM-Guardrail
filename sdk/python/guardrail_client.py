from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class GuardrailClient:
    base_url: str
    api_key: str
    timeout: float = 30.0

    def chat(
        self,
        prompt: str,
        *,
        model: str | None = None,
        backend: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
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

        response = httpx.post(
            self.base_url.rstrip("/") + "/chat",
            headers={"X-Api-Key": self.api_key},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
