"""
Approximate token pricing (USD per 1K tokens) for analytics cost estimates.
Uses a blended input/output rate for simplicity. Not used for billing — display only.
"""

# (input_price + output_price) / 2 per 1K tokens, approximate as of mid-2025
_RATES: dict[str, float] = {
    # OpenAI
    "openai:gpt-4o":            0.00625,   # $0.0025 in / $0.01 out
    "openai:gpt-4o-mini":       0.000225,  # $0.00015 in / $0.0006 out
    "openai:gpt-4-turbo":       0.025,
    "openai:gpt-3.5-turbo":     0.001,
    # Anthropic
    "anthropic:claude-opus-4":           0.0225,   # $0.015 in / $0.075 out
    "anthropic:claude-sonnet-4-20250514": 0.009,   # $0.003 in / $0.015 out
    "anthropic:claude-haiku-4":          0.00125,  # $0.00025 in / $0.00125 out (approx)
    # Groq (very cheap)
    "groq:llama-3.1-8b-instant":   0.00006,
    "groq:llama-3.3-70b-versatile": 0.0003,
    "groq:openai/gpt-oss-20b":      0.0001,
    # Gemini
    "gemini:gemini-2.0-flash":   0.0003,
    "gemini:gemini-1.5-pro":     0.00875,
    # Self-hosted / free
    "ollama": 0.0,
    "mock":   0.0,
    "openai_compatible": 0.001,  # unknown — use a rough default
}

# Fallback rates when the exact model isn't in the table
_BACKEND_FALLBACK: dict[str, float] = {
    "openai":            0.005,
    "anthropic":         0.009,
    "groq":              0.0001,
    "gemini":            0.001,
    "ollama":            0.0,
    "mock":              0.0,
    "openai_compatible": 0.001,
}


def estimate_cost_usd(backend: str, model: str, total_tokens: int) -> float:
    """Return a rough cost estimate in USD for display in analytics."""
    rate = _RATES.get(f"{backend}:{model}") \
        or _RATES.get(backend) \
        or _BACKEND_FALLBACK.get(backend, 0.001)
    return round(rate * total_tokens / 1000, 6)
