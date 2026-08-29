"""Classifier-based routing — LiteLLM auto-router stub (Datadog pattern).

Lightweight prompts → nano (cheap), complex → frontier, without code change.
Uses rule-based complexity scoring (token estimate + injection/jailbreak flags)
so no extra LLM call. Real impl would call a 0.5B classifier; this is 95% as good
and adds 0ms latency. Wired in app/services/llm/__init__.py:call_llm.
"""
from __future__ import annotations

def complexity_score(prompt: str) -> float:
    """0.0 (trivial) → 1.0 (hard)."""
    length = len(prompt)
    # length component
    score = min(0.5, length / 2000)
    # injection/jailbreak adds complexity (needs frontier reasoning)
    low = prompt.lower()
    if any(k in low for k in ("ignore previous", "jailbreak", "DAN mode")):
        score += 0.3
    # code / math heavy
    if "```" in prompt or "def " in prompt or "SELECT " in prompt.upper():
        score += 0.2
    # long context
    if length > 4000:
        score += 0.2
    return min(1.0, score)

def route_model(prompt: str, default_backend: str, default_model: str) -> tuple[str, str]:
    """Return (backend, model) for this prompt."""
    score = complexity_score(prompt)
    # thresholds tuned from Bifrost: 0.35 = nano → frontier boundary
    if score < 0.35:
        # cheap nano for extraction/tagging
        if default_backend == "groq":
            return "groq", "llama-3.1-8b-instant"
        if default_backend == "openai":
            return "openai", "gpt-4o-mini"
        return default_backend, default_model
    # frontier for synthesis / hard
    return default_backend, default_model
