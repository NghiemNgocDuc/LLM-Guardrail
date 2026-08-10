"""Tests for outgoing guardrail webhook signing (X-Guardrail-Signature)."""
import asyncio
import hashlib
import hmac
import json
import time

from app.routers.chat import _fire_webhook
from app.utils.webhook_signature import sign_payload, verify_signature


class _FakeResponse:
    status_code = 200


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json or {}, "headers": headers or {}})
        return _FakeResponse()


def _install(monkeypatch, client, secret=None):
    async def _validate(url):
        return None

    monkeypatch.setattr("app.routers.chat.validate_webhook_url_resolved", _validate)
    monkeypatch.setattr("app.routers.chat.get_http_client", lambda: client)
    return client


def _run(client, payload, secret):
    asyncio.run(_fire_webhook("https://hook.example.com/receive", payload, webhook_secret=secret))


def test_signed_webhook_carries_hmac_headers(monkeypatch):
    client = _FakeClient()
    _install(monkeypatch, client)
    payload = {"event": "guardrail_fired", "fired_rule": "pii_detected"}

    _run(client, payload, secret="test-secret")

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://hook.example.com/receive"
    assert call["json"] == payload
    assert call["headers"]["Content-Type"] == "application/json"

    signature = call["headers"]["X-Guardrail-Signature"]
    timestamp = call["headers"]["X-Guardrail-Timestamp"]
    assert signature.startswith("v1,")

    body = json.dumps(payload, separators=(",", ":")).encode()
    expected = hmac.new(
        b"test-secret",
        f"{timestamp}.{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert signature == f"v1,{expected}"


def test_unsigned_webhook_when_no_secret(monkeypatch):
    client = _FakeClient()
    _install(monkeypatch, client)

    _run(client, {"event": "guardrail_fired"}, secret=None)

    assert len(client.calls) == 1
    headers = client.calls[0]["headers"]
    assert "X-Guardrail-Signature" not in headers
    assert "X-Guardrail-Timestamp" not in headers


def test_signature_changes_with_payload(monkeypatch):
    client_a, client_b = _FakeClient(), _FakeClient()
    _install(monkeypatch, client_a)
    _run(client_a, {"event": "guardrail_fired", "reason": "a"}, secret="s")
    _install(monkeypatch, client_b)
    _run(client_b, {"event": "guardrail_fired", "reason": "b"}, secret="s")

    sig_a = client_a.calls[0]["headers"]["X-Guardrail-Signature"]
    sig_b = client_b.calls[0]["headers"]["X-Guardrail-Signature"]
    assert sig_a != sig_b


def test_mismatched_secret_fails_receiver_verification(monkeypatch):
    client = _FakeClient()
    _install(monkeypatch, client)
    payload = {"event": "guardrail_fired"}

    _run(client, payload, secret="sender-secret")

    signature = client.calls[0]["headers"]["X-Guardrail-Signature"]
    timestamp = client.calls[0]["headers"]["X-Guardrail-Timestamp"]
    body = json.dumps(payload, separators=(",", ":")).encode()
    wrong = hmac.new(
        b"receiver-secret",
        f"{timestamp}.{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert signature != f"v1,{wrong}"


def _signed(payload, secret, skew=0):
    signature, timestamp = sign_payload(payload, secret)
    return signature, str(int(time.time()) + skew), payload


def test_verify_signature_accepts_valid_sig():
    payload = {"event": "guardrail_fired", "fired_rule": "toxic_content"}
    signature, timestamp, body = _signed(payload, "shared-secret")
    assert verify_signature(body, "shared-secret", signature, timestamp)


def test_verify_signature_rejects_tampered_body():
    payload = {"event": "guardrail_fired", "fired_rule": "toxic_content"}
    signature, timestamp, body = _signed(payload, "shared-secret")
    body = dict(body)
    body["fired_rule"] = "pii_detected"
    assert not verify_signature(body, "shared-secret", signature, timestamp)


def test_verify_signature_rejects_wrong_secret():
    payload = {"event": "guardrail_fired"}
    signature, timestamp, body = _signed(payload, "sender-secret")
    assert not verify_signature(body, "receiver-secret", signature, timestamp)


def test_verify_signature_rejects_expired_timestamp():
    payload = {"event": "guardrail_fired"}
    signature, timestamp, body = _signed(payload, "shared-secret", skew=-3600)
    assert not verify_signature(body, "shared-secret", signature, timestamp)


def test_verify_signature_rejects_malformed_header():
    assert not verify_signature({"event": "x"}, "s", "no-prefix", "123")
    assert not verify_signature({"event": "x"}, "s", "garbage", "not-a-timestamp")