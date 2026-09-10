"""
Audience-bound capability tokens + receipt signing — Microsoft MCP 2026
confused-deputy fix (OAuth 2.1 PKCE, audience-bound tokens).

A raw capability (`cap_...`) is bearer-by-possession. Binding it to an
audience (e.g. `mandate-gateway:8182`) means a token minted for one server
cannot be replayed against another — the exact control Microsoft's 2026
guidance requires. Receipts are HMAC-signed so evidence can't be forged.

Stateless HMAC (no migration): aud_token = hex(hmac(SECRET, f"{cap_id}.{aud}")).
"""
from __future__ import annotations

import hashlib
import hmac
import os


def gateway_audience() -> str:
    return os.getenv("MANDATE_GATEWAY_AUDIENCE", "mandate-gateway:8182")


def _secret() -> bytes:
    try:
        from app.config import get_settings
        s = get_settings().SECRET_KEY or ""
    except Exception:
        s = ""
    return (s or "dev-only-test-secret").encode()


def sign_audience(capability_id: str, audience: str | None = None) -> str:
    aud = audience or gateway_audience()
    return hmac.new(_secret(), f"{capability_id}.{aud}".encode(), hashlib.sha256).hexdigest()


def verify_audience(capability_id: str, audience: str, token: str) -> bool:
    if not audience or not token:
        return False
    expected = sign_audience(capability_id, audience)
    return hmac.compare_digest(expected, token)


def enforce_audience() -> bool:
    return os.getenv("MANDATE_GATEWAY_ENFORCE_AUD", "false").lower() in ("1", "true", "yes")


def sign_receipt(receipt_id: str, decision: str) -> str:
    return hmac.new(_secret(), f"{receipt_id}.{decision}".encode(), hashlib.sha256).hexdigest()


def verify_receipt(receipt_id: str, decision: str, signature: str) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign_receipt(receipt_id, decision), signature)
