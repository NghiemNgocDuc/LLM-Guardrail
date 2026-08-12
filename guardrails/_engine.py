"""Guardrail engine selection — compiled Rust (`guardrail_core`) or pure Python.

Controlled by the `GUARDRAIL_ENGINE` setting (app/config.py, default "rust"):

  - "rust"   → use the compiled PyO3 extension when importable
  - "python" → always use the original Python implementation

The Rust path is fail-open: any import error or runtime error at an individual
check call site falls back to the Python implementation, so the extension is
never a hard requirement to run the app (a machine without a Rust toolchain
simply uses Python).
"""
from __future__ import annotations

import os

_MODULE = None
_AVAILABLE: bool | None = None


def _load():
    """Import guardrail_core once; None when it is unavailable."""
    global _MODULE, _AVAILABLE
    if _AVAILABLE is None:
        try:
            import guardrail_core

            _MODULE = guardrail_core
            _AVAILABLE = True
        except Exception:  # pragma: no cover - environment dependent
            _MODULE = None
            _AVAILABLE = False
    return _MODULE


def module():
    """The guardrail_core module, or None when it is not importable."""
    return _load()


def enabled() -> bool:
    """True when the Rust engine should be used for the next check."""
    flag = os.environ.get("GUARDRAIL_ENGINE")
    if flag is None:
        try:
            from app.config import get_settings

            flag = get_settings().GUARDRAIL_ENGINE
        except Exception:  # pragma: no cover - defensive
            flag = "rust"
    if str(flag).strip().lower() in ("python", "py"):
        return False
    return _load() is not None


def reset() -> None:
    """Forget the cached import result (used by tests / dev reloads)."""
    global _MODULE, _AVAILABLE
    _MODULE = None
    _AVAILABLE = None
