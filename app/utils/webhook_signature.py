"""
Signing and verification helpers for guardrail webhooks (HMAC-SHA256).

Signed request format delivered by /chat:

    X-Guardrail-Signature: v1,<hex digest of hmac-sha256(secret, "{timestamp}.{body}")>
    X-Guardrail-Timestamp: <unix seconds>

Verification mirrors the well-known Stripe/Svix scheme: recompute the digest
over the exact request body bytes and compare with hmac.compare_digest, with a
replay window guard.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time


def payload_bytes(payload: dict | bytes | str) -> bytes:
    if isinstance(payload, dict):
        return json.dumps(payload, separators=(",", ":")).encode()
    if isinstance(payload, str):
        return payload.encode()
    return payload


def sign_payload(payload: dict, secret: str, timestamp: int | None = None) -> tuple[str, str]:
    """Return (signature_header_value, timestamp) for a JSON payload."""
    ts = str(int(timestamp) if timestamp is not None else int(time.time()))
    body = payload_bytes(payload)
    digest = hmac.new(secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"v1,{digest}", ts


def verify_signature(
    payload: dict | bytes | str,
    secret: str,
    signature: str,
    timestamp: str,
    max_skew_s: int = 300,
) -> bool:
    """True when the signature is valid, has the v1 prefix, and is fresh."""
    if not signature.startswith("v1,"):
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > max_skew_s:
        return False
    body = payload_bytes(payload)
    expected = hmac.new(secret.encode(), f"{timestamp}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature[len("v1,"):], expected)