import json
from app.http_client import get_http_client
from app.services.llm.base import BaseLLMAdapter, LLMResponse, LLMStreamChunk
from app.config import enforce_private_llm, get_settings

settings = get_settings()


class OllamaAdapter(BaseLLMAdapter):
    """Calls a local/remote Ollama instance — no API key required."""

    async def _verify_local_runtime(self, client, model: str) -> None:
        if not settings.PRIVATE_MODE:
            return
        # A local HTTP endpoint can still proxy an Ollama cloud model. Check
        # server policy and the selected model before sending any prompt.
        status = await client.get(f"{settings.OLLAMA_BASE_URL}/api/status", timeout=5.0)
        status.raise_for_status()
        status_data = status.json()
        cloud = status_data.get("cloud", {}) if isinstance(status_data, dict) else {}
        if not isinstance(cloud, dict) or cloud.get("disabled") is not True:
            raise ValueError("PRIVATE_MODE requires Ollama to run with OLLAMA_NO_CLOUD=1")
        shown = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/show", json={"model": model}, timeout=5.0,
        )
        shown.raise_for_status()
        details = shown.json()
        if (
            not isinstance(details, dict)
            or details.get("error")
            or details.get("remote_host")
            or details.get("remote_model")
            or not isinstance(details.get("details"), dict)
            or not details["details"].get("format")
        ):
            raise ValueError("PRIVATE_MODE requires the configured model to be downloaded locally")

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int) -> LLMResponse:
        enforce_private_llm("ollama", model, settings=settings)
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        client = get_http_client()
        await self._verify_local_runtime(client, model)
        resp = await client.post(
            url,
            json={
                "model": model,
                "stream": False,
                **({"think": False} if settings.PRIVATE_MODE and model.startswith("qwen3") else {}),
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
        enforce_private_llm("ollama", model, settings=settings)
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        client = get_http_client()
        await self._verify_local_runtime(client, model)
        async with client.stream(
            "POST", url,
            json={
                "model": model,
                "stream": True,
                **({"think": False} if settings.PRIVATE_MODE and model.startswith("qwen3") else {}),
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
                    if settings.PRIVATE_MODE:
                        raise ValueError("Private Ollama returned an invalid stream") from None
                    continue

                if settings.PRIVATE_MODE and (not isinstance(data, dict) or data.get("error")):
                    raise ValueError("Private Ollama failed to complete the stream")

                if data.get("done"):
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield LLMStreamChunk(token=content, done=False, model=model, backend="ollama")
                    yield LLMStreamChunk(
                        token="", done=True,
                        input_tokens=data.get("prompt_eval_count", 0),
                        output_tokens=data.get("eval_count", 0),
                        model=model, backend="ollama",
                    )
                    return
                else:
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield LLMStreamChunk(token=content, done=False, model=model, backend="ollama")
            if settings.PRIVATE_MODE:
                raise ValueError("Private Ollama stream ended without a completion marker")
