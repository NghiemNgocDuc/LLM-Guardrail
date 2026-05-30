import pytest

import app.services.llm as llm
from app.services.llm.groq import GroqAdapter


def test_default_backend_resolves_to_groq(monkeypatch):
    monkeypatch.setattr(llm.settings, "DEFAULT_LLM_BACKEND", "groq")

    adapter, backend, model = llm.resolve_adapter(None, None, None, None)

    assert backend == "groq"
    assert model == "openai/gpt-oss-20b"
    assert isinstance(adapter, GroqAdapter)


@pytest.mark.asyncio
async def test_groq_adapter_requires_api_key(monkeypatch):
    from app.services.llm import groq

    monkeypatch.setattr(groq.settings, "GROQ_API_KEY", "")

    with pytest.raises(ValueError, match="GROQ_API_KEY is not configured"):
        await GroqAdapter().complete("ping", "openai/gpt-oss-20b", 0.1, 8)
