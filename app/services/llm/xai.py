"""xAI Grok adapter (xAI / SpaceX) — OpenAI-compatible.

Uses the same wire as OpenAI (chat completions) at https://api.x.ai/v1.
Set XAI_API_KEY (or GROK_API_KEY alias) in .env. Works with Grok-4, Grok-3, etc.
"""
from app.services.llm.openai import OpenAIAdapter

class XAIAdapter(OpenAIAdapter):
    """Grok adapter — inherits OpenAI wire, just different env keys + base URL."""
    def __init__(self):
        # Reuse OpenAI logic but override env lookup
        super().__init__()
        self._is_xai = True

    async def complete(self, prompt: str, model: str, temperature: float, max_tokens: int):
        from app.config import get_settings
        settings = get_settings()
        # allow explicit model or default
        api_key = settings.XAI_API_KEY or settings.GROK_API_KEY or settings.OPENAI_COMPATIBLE_API_KEY
        base_url = settings.XAI_BASE_URL or settings.GROK_BASE_URL or "https://api.x.ai/v1"
        if not api_key:
            raise ValueError("XAI_API_KEY (or GROK_API_KEY) not set for Grok")
        # Temporarily patch settings for parent
        old_key, old_base = settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL
        try:
            settings.OPENAI_API_KEY = api_key
            settings.OPENAI_BASE_URL = base_url
            return await super().complete(prompt, model, temperature, max_tokens)
        finally:
            settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL = old_key, old_base

    async def stream(self, prompt: str, model: str, temperature: float, max_tokens: int):
        from app.config import get_settings
        settings = get_settings()
        api_key = settings.XAI_API_KEY or settings.GROK_API_KEY or settings.OPENAI_COMPATIBLE_API_KEY
        base_url = settings.XAI_BASE_URL or settings.GROK_BASE_URL or "https://api.x.ai/v1"
        if not api_key:
            raise ValueError("XAI_API_KEY not set for Grok")
        old_key, old_base = settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL
        try:
            settings.OPENAI_API_KEY = api_key
            settings.OPENAI_BASE_URL = base_url
            async for chunk in super().stream(prompt, model, temperature, max_tokens):
                yield chunk
        finally:
            settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL = old_key, old_base
