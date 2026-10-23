"""Verify local sessions and Clerk signatures with the real JWT backend."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import deps


@pytest.fixture(scope="module")
def clerk_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    pem = public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    jwk = json.loads(deps.jwt.algorithms.RSAAlgorithm.to_jwk(public))
    jwk["kid"] = "test-clerk-key"
    return private, pem, jwk


def test_local_session_tokens_keep_their_type_and_reject_wrong_signatures(monkeypatch):
    monkeypatch.setattr(deps.settings, "SECRET_KEY", "local-test-signing-key-" + "a" * 32)
    for factory, expected in [(deps.create_access_token, "access"), (deps.create_refresh_token, "refresh")]:
        token = factory("test-user")
        claims = deps.decode_token(token)
        assert claims["sub"] == "test-user" and claims["type"] == expected
        with monkeypatch.context() as context:
            context.setattr(deps.settings, "SECRET_KEY", "different-test-signing-key-" + "b" * 32)
            with pytest.raises(HTTPException) as rejected:
                deps.decode_token(token)
            assert rejected.value.status_code == 401


@pytest.mark.parametrize("source", ["pem", "jwks"])
@pytest.mark.parametrize("expired", [False, True])
def test_clerk_verifies_real_rsa_signatures_and_expiration(monkeypatch, clerk_keys, source, expired):
    private, pem, jwk = clerk_keys
    monkeypatch.setattr(deps, "_clerk_public_key", None)
    monkeypatch.setattr(deps, "_jwks_cache", None)
    monkeypatch.setattr(deps.settings, "CLERK_JWT_KEY", pem if source == "pem" else "")
    monkeypatch.setattr(deps.settings, "CLERK_JWKS_URL", "https://clerk.example.test/jwks")

    class Client:
        async def get(self, url, **kwargs):
            assert source == "jwks" and url == deps.settings.CLERK_JWKS_URL
            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"keys": [jwk]}
            return Response()

    monkeypatch.setattr(deps, "get_http_client", Client)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 5)
    token = deps.jwt.encode({"sub": "clerk-user", "exp": expiry}, private, algorithm="RS256", headers={"kid": jwk["kid"]})
    if expired:
        with pytest.raises(HTTPException) as rejected:
            asyncio.run(deps._verify_clerk_token(token))
        assert rejected.value.status_code == 401
    else:
        assert asyncio.run(deps._verify_clerk_token(token))["sub"] == "clerk-user"


def test_malformed_clerk_token_returns_unauthorized():
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(deps._verify_clerk_token("malformed"))
    assert rejected.value.status_code == 401
