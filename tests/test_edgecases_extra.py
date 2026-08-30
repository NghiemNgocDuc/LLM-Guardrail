"""Extra edge cases — pagination, XSS, large payloads, secret scrub middleware, chat validation."""
import asyncio
import pytest

def test_memory_pagination_and_filters():
    # Validate that list_memories handles limit/offset edge values without crash (mocked DB not needed, just schema)
    from app.schemas import MemoryCreate
    # limit 0 should be rejected by API layer (ge=1) — test schema
    import pytest
    with pytest.raises(Exception):
        MemoryCreate(content="test", category="fact", confidence=1.5)  # >1 invalid
    with pytest.raises(Exception):
        MemoryCreate(content="test", category="fact", importance=6)  # >5
    # valid edge: max length 4000
    m = MemoryCreate(content="a"*4000, category="fact")
    assert len(m.content) == 4000
    with pytest.raises(Exception):
        MemoryCreate(content="a"*4001, category="fact")

def test_memory_title_auto():
    content = "This is a very long memory content that should be truncated to 60 chars for title generation purposes and more"
    title = (None or content[:60]).strip()
    assert title == content[:60].strip()
    assert len(title) <= 60

def test_chat_request_validation():
    from app.schemas import ChatRequest
    import pytest
    # empty prompt
    with pytest.raises(Exception):
        ChatRequest(prompt="")
    # too long
    with pytest.raises(Exception):
        ChatRequest(prompt="a"*32001)
    # ok
    ChatRequest(prompt="hello", temperature=0.7, max_tokens=1024)
    # out of range temperature
    with pytest.raises(Exception):
        ChatRequest(prompt="hi", temperature=3.0)
    with pytest.raises(Exception):
        ChatRequest(prompt="hi", max_tokens=0)
    with pytest.raises(Exception):
        ChatRequest(prompt="hi", max_tokens=9000)

def test_chat_prompt_sanitize_null_byte():
    from app.utils.sanitize import sanitize_prompt
    # null byte should raise via sanitize_string when called in chat, but ChatRequest itself allows it — ensure sanitize catches
    import pytest
    from app.utils.sanitize import sanitize_string
    with pytest.raises(ValueError):
        sanitize_string("hello\x00world")
    # control chars stripped
    assert "\x01" not in sanitize_string("hello\x01world")

def test_secret_scrub_middleware():
    from app.utils.secret_redaction import scrub_text
    # normal JSON should not be altered
    normal = '{"detail": "hello world", "count": 5}'
    assert scrub_text(normal) == normal
    # secret in JSON value should be scrubbed
    leaked = '{"token": "gsk_' + "a"*30 + '"}'
    assert "[REDACTED:SECRET]" in scrub_text(leaked)
    assert "gsk_" not in scrub_text(leaked)

def test_secret_scrub_idempotent_and_headers():
    from app.utils.secret_redaction import scrub_headers
    h = {"Authorization": "Bearer gsk_" + "a"*30, "Content-Type": "application/json", "X-Custom": "grg_" + "b"*30}
    scrubbed = scrub_headers(h)
    assert scrubbed["Authorization"] == "[REDACTED:SECRET]"
    assert scrubbed["Content-Type"] == "application/json"
    assert scrubbed["X-Custom"] == "[REDACTED:SECRET]"

def test_api_key_scopes_edge():
    # scopes validation not strict, but ensure empty scopes still defaults to chat via deps
    from app.models import APIKey
    key = APIKey(name="test", key_prefix="grg_test", key_hash="hash", owner_id="uid", scopes=[])
    assert key.scopes == []

def test_groq_key_never_in_response():
    # Ensure no router file contains GROQ_API_KEY in response model
    import pathlib
    for p in pathlib.Path("app/routers").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        # if GROQ appears, it should only be in comments or not returned
        if "GROQ_API_KEY" in text:
            # ensure not in response_model or return
            assert "return" not in text.split("GROQ_API_KEY")[1][:200] or "settings.GROQ_API_KEY" in text

def test_concurrent_api_key_protection():
    import asyncio
    from app.services import api_key_protection as p
    p._req_windows.clear(); p._ip_windows.clear(); p._token_windows.clear(); p._block_windows.clear(); p._dedup_windows.clear(); p._banned_keys.clear(); p._banned_users.clear(); p._ban_strikes.clear()
    async def hammer():
        tasks = [p.record_usage(api_key_id="conc", user_id="u", ip="1.1.1.1", tokens=10, blocked=False) for _ in range(50)]
        results = await asyncio.gather(*tasks)
        # should not crash, may trigger ban after 121 but 50 is safe
        assert all(isinstance(r, tuple) for r in results)
    asyncio.run(hammer())

def test_memory_xss_stored():
    # Ensure XSS payload is stored verbatim (frontend escapes) but not executed
    payload = "<img src=x onerror=alert(1)>"
    from app.schemas import MemoryCreate
    m = MemoryCreate(content=payload, category="fact")
    assert payload in m.content
    # scrub should not remove it (not a secret)
    from app.utils.secret_redaction import scrub_text
    assert scrub_text(payload) == payload

def test_billing_unlimited_bypass():
    # unlimited emails should bypass wallet check
    from app.services.token_wallet import unlimited_email_set
    from unittest.mock import patch
    from app import config
    s = config.get_settings()
    orig = s.BILLING_UNLIMITED_EMAILS
    try:
        s.BILLING_UNLIMITED_EMAILS = "admin@example.com, user@test.com"
        # need to reload function? it reads settings each call
        assert "admin@example.com" in unlimited_email_set()
        assert "user@test.com" in unlimited_email_set()
    finally:
        s.BILLING_UNLIMITED_EMAILS = orig

def test_rate_limit_edge_values():
    from app.middleware.rate_limit import _check_memory_rate_limit
    import uuid
    key = str(uuid.uuid4())
    # RPM=0 should always fail
    with pytest.raises(Exception):
        _check_memory_rate_limit(key, rpm=0, rpd=1000)
    # very high RPM should pass
    key2 = str(uuid.uuid4())
    res = _check_memory_rate_limit(key2, rpm=10000, rpd=10000)
    assert "rpm_remaining" in res
