"""
ML 2nd-stage injection detector — Veto-style Go regex hot path -> Python inference.

Stage 1 (regex, in input.py) catches classic `ignore previous instructions`.
Stage 2 (here) catches paraphrased / obfuscated injections that regex misses,
using protectai/deberta-v3-base-prompt-injection-v2 when installed, with a
lightweight heuristic fallback so the gateway works with zero extra deps.

Fail-open by design: if the model is not installed or errors, the heuristic
fallback still runs; the caller keeps the regex verdict on total failure.
Set policy ml_injection=block to enforce, warn to flag, off (default) to
skip. Mirrors veto-core gateway -> inference split and AgentDojo
TransformersBasedPIDetector.
"""
from __future__ import annotations

import re
import threading

DEFAULT_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"
DEFAULT_THRESHOLD = 0.5

# Heuristic signals for when the transformer is unavailable.
# Each is (regex, weight). Tuned to catch obfuscation without flagging benign.
_HEURISTIC_SIGNALS: list[tuple[str, float]] = [
    (r"(?i)\bignore\b.{0,30}\b(instructions?|directives?|orders?|guidance)\b", 0.6),
    (r"(?i)\bdisregard\b.{0,30}\b(prompt|instructions?|rules?|directives?|prior)\b", 0.6),
    (r"(?i)\bforget\b.{0,20}\b(everything|all|previous)\b", 0.5),
    (r"(?i)\b bypass\b.{0,20}\b(policy|filter|safety|guardrail)", 0.5),
    (r"(?i)\bDAN\b|\bjail ?break\b|\bdo anything now\b", 0.7),
    (r"(?i)system prompt|hidden instructions", 0.5),
    (r"(?i)\bexfiltrat\w*\b", 0.45),
    (r"(?i)imperative[:\s]+(you must|do not tell|do not reveal)", 0.4),
    (r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]", 0.4),  # zero-width / bidi obfuscation
    (r"(?i)(i+g+n+o+r+e+|d+i+s+r+e+g+a+r+d)", 0.5),  # stretched evasion
]

_lock = threading.Lock()
_pipeline = None
_pipeline_model: str | None = None
_pipeline_error: str | None = None


def _load_pipeline(model: str):
    global _pipeline, _pipeline_model, _pipeline_error
    with _lock:
        if _pipeline is not None and _pipeline_model == model:
            return _pipeline
        try:
            import torch  # noqa: F401
            from transformers import pipeline  # noqa: F401
        except Exception as e:  # pragma: no cover - missing optional dep
            _pipeline_error = f"transformers/torch unavailable: {e}"
            return None
        try:
            import torch
            from transformers import pipeline as hf_pipeline
            device = 0 if torch.cuda.is_available() else -1
            _pipeline = hf_pipeline("text-classification", model=model, device=device, truncation=True)
            _pipeline_model = model
            _pipeline_error = None
            return _pipeline
        except Exception as e:
            _pipeline_error = str(e)[:200]
            return None


def heuristic_score(text: str) -> float:
    score = 0.0
    for pattern, weight in _HEURISTIC_SIGNALS:
        try:
            if re.search(pattern, text):
                score += weight
        except re.error:
            continue
    # Cap at 0.95; two independent signals is enough to fire.
    return min(score, 0.95)


def detect(text: str, model: str = DEFAULT_MODEL, threshold: float = DEFAULT_THRESHOLD) -> tuple[bool, float, str] | None:
    """Return (is_injection, score, backend) or None when unavailable/skipped.

    Backend is transformers | heuristic. Never raises — fail-open.
    """
    if not text or not text.strip():
        return (False, 0.0, "heuristic")
    pipe = _load_pipeline(model)
    if pipe is not None:
        try:
            out = pipe(text[:512])[0]
            label = str(out.get("label", ""))
            raw = float(out.get("score", 0.0))
            # protectai uses SAFE as safe label
            safety = raw if label.upper() == "SAFE" else 1.0 - raw
            return (safety < threshold, 1.0 - safety, "transformers")
        except Exception:
            pass
    # Heuristic fallback — fires at >=0.8 (two signals or one strong).
    score = heuristic_score(text)
    return (score >= 0.8, score, "heuristic")


def status() -> dict:
    return {
        "model": _pipeline_model or DEFAULT_MODEL,
        "loaded": _pipeline is not None,
        "error": _pipeline_error,
        "threshold": DEFAULT_THRESHOLD,
    }
