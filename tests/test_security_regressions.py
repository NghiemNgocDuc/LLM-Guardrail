"""Regression tests for security fixes (traversal, JWT alg pinning, billing, SSRF, XFF)."""
import asyncio
import os
import socket
import sys

import pytest
from fastapi import Request

import app.deps as deps
import app.demo_limits as demo_limits
from app.config import Settings
from app.utils import url_validation
from main import _safe_static_target


# ─── 1. Static file path traversal ────────────────────────────────────────────

def test_static_target_allows_files_inside_root(tmp_path, monkeypatch):
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("idx")
    (root / "secret.txt").write_text("s3cr3t")
    monkeypatch.setattr("main._static_root", root.resolve())

    assert _safe_static_target("index.html") is not None
    assert _safe_static_target("secret.txt") is not None


def test_static_target_rejects_traversal(tmp_path, monkeypatch):
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("idx")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    monkeypatch.setattr("main._static_root", root.resolve())

    assert _safe_static_target("") is None
    assert _safe_static_target("../outside.txt") is None
    assert _safe_static_target("a/../../outside.txt") is None
    assert _safe_static_target("a/../secret.txt") is None
    assert _safe_static_target("..\\outside.txt") is None
    assert _safe_static_target("x\x00.txt") is None
    assert _safe_static_target("assets/..") is None
    assert _safe_static_target("missing.txt") is None
    assert _safe_static_target("assets") is None  # directory, not a file


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_static_target_rejects_symlink_escape(tmp_path, monkeypatch):
    import main as main_mod

    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("idx")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    try:
        (root / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted here")
    monkeypatch.setattr(main_mod, "_static_root", root.resolve())

    assert _safe_static_target("link.txt") is None


# ─── 2. Clerk JWT algorithm pinning ──────────────────────────────────────────

class _FakeJWKSClient:
    def __init__(self, payload):
        self._payload = payload

    async def get(self, url, timeout=None):
        payload = self._payload

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return Resp()


async def _run(coro):
    return await coro


def test_clerk_pem_path_pins_rs256(monkeypatch):
    monkeypatch.setattr(deps.settings, "CLERK_JWT_KEY", "-----BEGIN PUBLIC KEY-----\nX\n-----END PUBLIC KEY-----")
    monkeypatch.setattr(deps, "_clerk_public_key", None)
    monkeypatch.setattr(deps.jwt, "get_unverified_header", lambda t: {"kid": "k1", "alg": "none"})
    calls = {}

    def fake_decode(token, key, algorithms=None, options=None):
        calls["algorithms"] = algorithms
        return {"sub": "u1"}

    monkeypatch.setattr(deps.jwt, "decode", fake_decode)
    monkeypatch.setattr(deps, "construct", lambda pem: "KEY")

    result = asyncio.run(_run(deps._verify_clerk_token("t")))
    assert result == {"sub": "u1"}
    assert calls["algorithms"] == ["RS256"]


def test_clerk_jwks_path_pins_rs256(monkeypatch):
    monkeypatch.setattr(deps.settings, "CLERK_JWT_KEY", "")
    monkeypatch.setattr(deps.settings, "CLERK_JWKS_URL", "https://clerk.example/.well-known/jwks.json")
    monkeypatch.setattr(deps, "_jwks_cache", None)
    monkeypatch.setattr(deps, "_jwks_cache_ts", 0.0)
    monkeypatch.setattr(deps.jwt, "get_unverified_header", lambda t: {"kid": "k1", "alg": "none"})
    monkeypatch.setattr(deps, "construct", lambda key_data: "KEY")
    monkeypatch.setattr(
        deps,
        "get_http_client",
        lambda: _FakeJWKSClient({"keys": [{"kid": "k1", "kty": "RSA", "n": "x", "e": "AQAB"}]}),
    )
    calls = {}

    def fake_decode(token, key, algorithms=None, options=None):
        calls["algorithms"] = algorithms
        return {"sub": "u2"}

    monkeypatch.setattr(deps.jwt, "decode", fake_decode)

    result = asyncio.run(_run(deps._verify_clerk_token("t")))
    assert result == {"sub": "u2"}
    assert calls["algorithms"] == ["RS256"]


# ─── 3. Billing unlimited-emails default ─────────────────────────────────────

def test_billing_unlimited_emails_has_no_default(monkeypatch):
    monkeypatch.delenv("BILLING_UNLIMITED_EMAILS", raising=False)
    s = Settings(_env_file=None)
    assert s.BILLING_UNLIMITED_EMAILS == ""


# ─── 4. SSRF: resolve-at-call-time checks ────────────────────────────────────

class _FakeLoop:
    def __init__(self, addrs, error=None):
        self._addrs = addrs
        self._error = error

    async def getaddrinfo(self, host, port=None, family=0, type=0, proto=0, flags=0):
        if self._error:
            raise self._error
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))
            for addr in self._addrs
        ]


def _patch_resolver(monkeypatch, addrs=None, error=None):
    monkeypatch.setattr(
        url_validation.asyncio,
        "get_running_loop",
        lambda: _FakeLoop(addrs or [], error=error),
    )


def _await(coro):
    """Run a coroutine on a dedicated loop so the patched get_running_loop is used."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_webhook_url_allows_public_resolution(monkeypatch):
    _patch_resolver(monkeypatch, addrs=["8.8.8.8"])
    assert _await(url_validation.validate_webhook_url_resolved("https://example.com/cb")) is None


def test_webhook_url_blocks_rebinding_to_loopback(monkeypatch):
    _patch_resolver(monkeypatch, addrs=["127.0.0.1"])
    with pytest.raises(ValueError):
        _await(url_validation.validate_webhook_url_resolved("https://example.com/cb"))


def test_webhook_url_blocks_any_private_answer(monkeypatch):
    _patch_resolver(monkeypatch, addrs=["8.8.8.8", "10.0.0.5"])
    with pytest.raises(ValueError):
        _await(url_validation.validate_webhook_url_resolved("https://example.com/cb"))


def test_webhook_url_blocks_ipv4_mapped_loopback(monkeypatch):
    _patch_resolver(monkeypatch, addrs=["::ffff:127.0.0.1"])
    with pytest.raises(ValueError):
        _await(url_validation.validate_webhook_url_resolved("https://example.com/cb"))


def test_webhook_url_blocks_resolution_failure(monkeypatch):
    _patch_resolver(monkeypatch, error=socket.gaierror(-2, "Name or service not known"))
    with pytest.raises(ValueError):
        _await(url_validation.validate_webhook_url_resolved("https://example.com/cb"))


def test_webhook_url_static_blocks_still_apply(monkeypatch):
    _patch_resolver(monkeypatch, addrs=["8.8.8.8"])
    with pytest.raises(ValueError):
        _await(url_validation.validate_webhook_url_resolved("http://localhost:9/cb"))
    with pytest.raises(ValueError):
        _await(url_validation.validate_webhook_url_resolved("file:///etc/passwd"))


# ─── 5. X-Forwarded-For trust in demo IP limits ──────────────────────────────

def _req(client_host, xff):
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    return Request(
        {
            "type": "http",
            "client": (client_host, 12345),
            "headers": headers,
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
        }
    )


def test_client_ip_ignores_spoofed_xff_from_public_peer():
    req = _req("1.2.3.4", "10.0.0.9")
    assert demo_limits.client_ip(req) == "1.2.3.4"


def test_client_ip_trusts_xff_from_proxy_peer():
    req = _req("10.1.1.1", "5.6.7.8")
    assert demo_limits.client_ip(req) == "5.6.7.8"


def test_client_ip_ignores_garbage_xff():
    req = _req("1.2.3.4", "not-an-ip")
    assert demo_limits.client_ip(req) == "1.2.3.4"


def test_client_ip_falls_back_without_peer():
    req = Request(
        {
            "type": "http",
            "client": None,
            "headers": [],
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    assert demo_limits.client_ip(req) == "unknown"