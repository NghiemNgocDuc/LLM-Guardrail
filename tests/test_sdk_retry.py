import json

import httpx
import pytest

from sdk.python.guardrail_client import GuardrailClient


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://mock"),
                response=self,
            )

    def json(self):
        return self._payload


class FakeStreamResponse:
    def __init__(self, status_code, lines=(), headers=None, error_after=None):
        self.status_code = status_code
        self._lines = lines
        self.headers = headers or {}
        self.error_after = error_after

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://mock"),
                response=self,
            )

    async def aiter_lines(self):
        for i, line in enumerate(self._lines):
            if self.error_after is not None and i >= self.error_after:
                raise RuntimeError("connection dropped mid-stream")
            yield line


class FakeStream:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


class FakeAsyncClient:
    def __init__(self, responses, call_log):
        # Shared list: the SDK builds a new AsyncClient per attempt, so pops
        # must consume from the same queue across attempts.
        self._responses = responses
        self._call_log = call_log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, **kwargs):
        self._call_log.append({"method": method, "url": url, "json": kwargs.get("json")})
        return FakeStream(self._responses.pop(0))


def _patch_sync_post(monkeypatch, call_log, responses):
    def post(url, **kwargs):
        call_log.append({"url": url, "json": kwargs.get("json")})
        return responses.pop(0)

    monkeypatch.setattr("httpx.post", post)


def _patch_async_client(monkeypatch, call_log, responses):
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(responses, call_log),
    )


def _patch_sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr("time.sleep", lambda s: calls.append(s))
    return calls


def test_chat_retries_on_429_then_succeeds(monkeypatch):
    sleeps   = _patch_sleeps(monkeypatch)
    call_log = []
    responses = [FakeResponse(429), FakeResponse(200, {"status": "delivered", "response": "ok"})]
    _patch_sync_post(monkeypatch, call_log, responses)

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    result = client.chat("hello")

    assert result == {"status": "delivered", "response": "ok"}
    assert len(call_log) == 2
    assert call_log[0]["url"] == "http://mock/chat"
    assert call_log[0]["json"]["prompt"] == "hello"
    assert sleeps == [1.0]  # exponential backoff, attempt 1


def test_chat_retries_on_402_then_succeeds(monkeypatch):
    sleeps   = _patch_sleeps(monkeypatch)
    call_log = []
    responses = [FakeResponse(402), FakeResponse(200, {"status": "delivered"})]
    _patch_sync_post(monkeypatch, call_log, responses)

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    result = client.chat("hello")

    assert result == {"status": "delivered"}
    assert len(call_log) == 2
    assert sleeps == [1.0]


def test_chat_does_not_retry_other_4xx(monkeypatch):
    sleeps   = _patch_sleeps(monkeypatch)
    call_log = []
    _patch_sync_post(monkeypatch, call_log, [FakeResponse(403)])

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    with pytest.raises(httpx.HTTPStatusError):
        client.chat("hello")

    assert len(call_log) == 1
    assert sleeps == []


def test_chat_no_retry_when_disabled(monkeypatch):
    sleeps   = _patch_sleeps(monkeypatch)
    call_log = []
    _patch_sync_post(monkeypatch, call_log, [FakeResponse(429)])

    client = GuardrailClient(base_url="http://mock", api_key="grg_key")
    with pytest.raises(httpx.HTTPStatusError):
        client.chat("hello")

    assert len(call_log) == 1
    assert sleeps == []


def test_chat_retries_exhausted(monkeypatch):
    sleeps   = _patch_sleeps(monkeypatch)
    call_log = []
    responses = [FakeResponse(429) for _ in range(4)]
    _patch_sync_post(monkeypatch, call_log, responses)

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    with pytest.raises(httpx.HTTPStatusError):
        client.chat("hello")

    assert len(call_log) == 4  # 1 initial + 3 retries
    assert sleeps == [1.0, 2.0, 4.0]


def test_chat_honors_retry_after_header(monkeypatch):
    sleeps   = _patch_sleeps(monkeypatch)
    call_log = []
    responses = [
        FakeResponse(429, headers={"Retry-After": "5"}),
        FakeResponse(200, {"status": "delivered"}),
    ]
    _patch_sync_post(monkeypatch, call_log, responses)

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    result = client.chat("hello")

    assert result == {"status": "delivered"}
    assert sleeps == [5.0]


@pytest.mark.asyncio
async def test_chat_stream_yields_sse_events(monkeypatch):
    call_log = []
    lines = [
        f'data: {json.dumps({"type": "token", "content": "He"})}',
        f'data: {json.dumps({"type": "token", "content": "llo"})}',
        f'data: {json.dumps({"type": "done", "status": "delivered"})}',
    ]
    _patch_async_client(monkeypatch, call_log, [FakeStreamResponse(200, lines=lines)])

    client = GuardrailClient(base_url="http://mock", api_key="grg_key")
    events = [e async for e in client.chat_stream("hello")]

    assert events == [
        {"type": "token", "content": "He"},
        {"type": "token", "content": "llo"},
        {"type": "done", "status": "delivered"},
    ]
    assert len(call_log) == 1
    assert call_log[0]["url"] == "http://mock/chat/stream"
    assert call_log[0]["json"]["prompt"] == "hello"


@pytest.mark.asyncio
async def test_chat_stream_retries_429_before_stream_starts(monkeypatch):
    sleeps = []
    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    call_log = []
    lines = [f'data: {json.dumps({"type": "done", "status": "delivered"})}']
    _patch_async_client(
        monkeypatch, call_log,
        [FakeStreamResponse(429), FakeStreamResponse(200, lines=lines)],
    )

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    events = [e async for e in client.chat_stream("hello")]

    assert events == [{"type": "done", "status": "delivered"}]
    assert len(call_log) == 2  # retried the 429 before any chunk arrived
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_chat_stream_never_retries_mid_stream(monkeypatch):
    call_log = []
    lines = [
        f'data: {json.dumps({"type": "token", "content": "He"})}',
        f'data: {json.dumps({"type": "token", "content": "llo"})}',
    ]
    _patch_async_client(
        monkeypatch, call_log,
        [FakeStreamResponse(200, lines=lines, error_after=1)],
    )

    client = GuardrailClient(base_url="http://mock", api_key="grg_key", with_retry=True)
    with pytest.raises(RuntimeError):
        events = [e async for e in client.chat_stream("hello")]

    assert len(call_log) == 1  # never retried a stream that already delivered chunks


@pytest.mark.asyncio
async def test_chat_stream_no_retry_when_disabled(monkeypatch):
    call_log = []
    _patch_async_client(monkeypatch, call_log, [FakeStreamResponse(429)])

    client = GuardrailClient(base_url="http://mock", api_key="grg_key")
    with pytest.raises(httpx.HTTPStatusError):
        events = [e async for e in client.chat_stream("hello")]

    assert len(call_log) == 1