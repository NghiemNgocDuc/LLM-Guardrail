"""MCP gates and SSE transport regressions; no live provider or database calls."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import mcp_server as mcp
from app.schemas import ChatResponse, GuardrailResult


def _auth(key="key-a", scopes=None):
    return mcp.MCPAuthContext(key_id=key, owner_id="owner-a", org_id="org-a", scopes=scopes if scopes is not None else ["chat", "skills:read"], is_authenticated=True, raw_key="grg_" + "a" * 40)


class _Request:
    def __init__(self, *, key="key-a", session_id=None, body=None):
        self.headers = {"X-Api-Key": key}
        self.query_params = {"session_id": session_id} if session_id else {}
        self.body = json.dumps(body).encode() if body is not None else b""

    async def is_disconnected(self):
        return False

    async def stream(self):
        yield self.body


@pytest.mark.parametrize("arguments", [None, [], "text", {"content": 42}, {"content": "ok", "filename": {}}, {"content": "ok", "extra": "unexpected"}])
@pytest.mark.asyncio
async def test_malformed_tool_arguments_return_tool_errors(arguments):
    result = await mcp._call_tool("scan_skill", arguments)
    assert result["isError"] is True
    assert "error" in json.loads(result["content"][0]["text"])


@pytest.mark.parametrize("arguments", [{"prompt": "hello", "temperature": True}, {"prompt": "hello", "temperature": float("nan")}, {"prompt": "hello", "max_tokens": 1.5}, {"prompt": "hello", "policy_json": "[]"}])
@pytest.mark.asyncio
async def test_chat_parameter_types_cannot_escape_validation(arguments):
    result = await mcp._call_tool("chat", arguments)
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_scanning_requires_its_explicit_scope_and_unauthenticated_context_executes_nothing():
    denied = await mcp._call_tool("scan_skill", {"content": "Run tests."}, _auth(scopes=["chat"]))
    assert denied["isError"] and "skills:read" in denied["content"][0]["text"]
    allowed = await mcp._call_tool("scan_skill", {"content": "Run tests."}, _auth(scopes=["skills:read"]))
    assert not allowed["isError"]
    unauthenticated = mcp.MCPAuthContext(key_id="", owner_id="", org_id=None, is_authenticated=False)
    assert (await mcp._call_tool("get_default_policy", {}, unauthenticated))["isError"]
    assert mcp._visible_tools(unauthenticated) == []
    assert "chat" not in {tool["name"] for tool in mcp._visible_tools(_auth(scopes=["skills:read"]))}


@pytest.mark.asyncio
async def test_description_verification_errors_fail_closed(monkeypatch):
    import app.services.tool_drift as drift
    def broken(description):
        raise RuntimeError("security service unavailable")
    monkeypatch.setattr(drift, "detect_poisoning", broken)
    result = await mcp._call_tool("get_default_policy", {})
    assert result["isError"] and "unavailable" in result["content"][0]["text"]


def test_detector_itself_does_not_hide_guard_failures(monkeypatch):
    from app.services.tool_drift import detect_poisoning
    from guardrails.input import InputGuardrail
    monkeypatch.setattr(InputGuardrail, "check", lambda self, text: (_ for _ in ()).throw(RuntimeError("scanner unavailable")))
    poisoned, reason = detect_poisoning("Return a helpful summary.")
    assert poisoned and "unavailable" in reason


@pytest.mark.asyncio
async def test_remote_chat_requires_transport_and_forbids_client_policy_override():
    direct = await mcp._call_tool("chat", {"prompt": "Explain guardrails."}, _auth())
    assert direct["isError"] and "transport context" in direct["content"][0]["text"]
    override = await mcp._call_tool("chat", {"prompt": "Explain guardrails.", "policy_json": '{"block_secrets": false}'}, _auth(), _Request())
    assert override["isError"] and "workspace policy" in override["content"][0]["text"]


@pytest.mark.asyncio
async def test_remote_chat_uses_actual_gateway_handler_and_commits_its_result(monkeypatch):
    import app.database as database
    import app.deps as deps
    import app.routers.chat as gateway
    calls = []
    class DB:
        committed = False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, model, key): return SimpleNamespace(id="owner-a", org_id="org-a", is_active=True)
        async def commit(self): self.committed = True
    db = DB()
    key = SimpleNamespace(id="key-a", owner_id="owner-a", org_id="org-a", scopes=["chat"])
    async def resolve(raw_key, session):
        assert raw_key == _auth().raw_key and session is db
        return key
    async def guarded_chat(**kwargs):
        calls.append(kwargs)
        return ChatResponse(request_id="gateway-request", response=None, status="input_blocked", input_guard=GuardrailResult(passed=False, check="policy", reason="Blocked by workspace policy"), output_guard=None, latency_ms=1, model="-", backend="mock")
    monkeypatch.setattr(database, "get_sessionmaker", lambda: lambda: db)
    monkeypatch.setattr(deps, "resolve_api_key", resolve)
    monkeypatch.setattr(gateway, "chat", guarded_chat)
    request = _Request()
    result = await mcp._call_tool("chat", {"prompt": "Explain guardrails.", "max_tokens": 32}, _auth(), request)
    assert not result["isError"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "input_blocked" and payload["response"] is None
    assert calls[0]["request"] is request and calls[0]["api_key"] is key
    assert calls[0]["body"].max_tokens == 32 and db.committed
    assert mcp._result_status({"result": result}) == ("input_blocked", True)


@pytest.mark.asyncio
async def test_gateway_http_denials_become_errors_without_provider_fallback(monkeypatch):
    async def denied(*args, **kwargs):
        raise HTTPException(status_code=429, detail="Token budget exceeded")
    monkeypatch.setattr(mcp, "_gateway_chat", denied)
    result = await mcp._call_tool("chat", {"prompt": "Explain guardrails."}, _auth(), _Request())
    assert result["isError"] and "Token budget exceeded" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_local_stdio_chat_still_works_without_remote_auth(monkeypatch):
    from app.services import llm
    async def local_provider(**kwargs):
        return SimpleNamespace(text="A helpful answer.", model="mock", backend="mock", input_tokens=2, output_tokens=3)
    monkeypatch.setattr(llm, "call_llm", local_provider)
    result = await mcp._call_tool("chat", {"prompt": "Explain guardrails."})
    assert not result["isError"] and json.loads(result["content"][0]["text"])["status"] == "delivered"


@pytest.mark.parametrize("body", [[], {"method": "tools/call", "params": []}, {"method": "tools/call", "params": "bad"}, {"method": "ping", "id": {}}, {"method": "ping", "id": float("nan")}])
@pytest.mark.asyncio
async def test_malformed_protocol_requests_return_jsonrpc_errors(body):
    response = await mcp._handle_request(body, _auth())
    assert "error" in response


@pytest.fixture
def transport(monkeypatch):
    audits = []
    async def authenticate(request):
        return _auth(key=request.headers["X-Api-Key"])
    async def audit(auth, tool, args, status):
        audits.append((auth.key_id, tool, status))
    monkeypatch.setattr(mcp, "_resolve_sse_auth", authenticate)
    monkeypatch.setattr(mcp, "_audit_log", audit)
    mcp._rate_limits.clear()
    app = mcp.get_mcp_app()
    return app, app.routes[0].endpoint, app.routes[1].endpoint, audits


@pytest.mark.asyncio
async def test_sse_returns_immediately_delivers_replies_and_binds_sessions_to_keys(transport):
    app, sse, message, audits = transport
    stream = await asyncio.wait_for(sse(_Request()), timeout=.5)
    endpoint = await asyncio.wait_for(anext(stream.body_iterator), timeout=.5)
    session_id = endpoint.split("session_id=")[1].strip()
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "scan_skill", "arguments": {"content": "Run tests."}}}
    intruder = await message(_Request(key="different-key", session_id=session_id, body=body))
    assert intruder.status_code == 404 and audits == []
    response = await message(_Request(session_id=session_id, body=body))
    assert response.status_code == 202
    reply = await asyncio.wait_for(anext(stream.body_iterator), timeout=.5)
    payload = json.loads(reply.removeprefix("data: ").strip())
    assert payload["id"] == 1 and not payload["result"]["isError"]
    assert audits == [("key-a", "scan_skill", "ok")]
    await stream.body_iterator.aclose()
    assert session_id not in app.state.mcp_sessions


@pytest.mark.asyncio
async def test_sse_timeout_and_cancellation_remove_session_state(transport, monkeypatch):
    app, sse, _, _ = transport
    monkeypatch.setattr(mcp, "SSE_SESSION_TIMEOUT", .01)
    stream = await sse(_Request())
    await anext(stream.body_iterator)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream.body_iterator), timeout=.5)
    assert not app.state.mcp_sessions
    monkeypatch.setattr(mcp, "SSE_SESSION_TIMEOUT", 10)
    stream = await sse(_Request()); await anext(stream.body_iterator)
    waiting = asyncio.create_task(anext(stream.body_iterator))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError): await waiting
    assert not app.state.mcp_sessions


@pytest.mark.asyncio
async def test_stateless_post_preserved_and_audit_reports_actual_blocked_outcome(transport):
    _, _, message, audits = transport
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "scan_skill", "arguments": {"content": "Gateway credential: grg_" + "a" * 40}}}
    response = await message(_Request(body=body))
    assert response.status_code == 200
    assert json.loads(response.body)["result"]["isError"] is False
    assert audits[-1] == ("key-a", "scan_skill", "input_blocked")
    malformed = await message(_Request(body=[]))
    assert malformed.status_code == 400 and "error" in json.loads(malformed.body)


def test_inferred_tool_schema_resolves_future_annotations():
    schema = mcp.TOOL_REGISTRY["chat"]["input_schema"]
    assert schema["properties"]["max_tokens"]["type"] == "integer"
    assert schema["properties"]["temperature"]["type"] == "number"
    assert "null" in schema["properties"]["backend"]["type"]


@pytest.mark.parametrize("scopes,expected", [([], []), (None, ["chat"])])
@pytest.mark.asyncio
async def test_explicit_empty_key_scopes_do_not_acquire_legacy_chat_permissions(monkeypatch, scopes, expected):
    import app.database as database
    import app.deps as deps
    class DB:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, model, identifier): return SimpleNamespace(id="owner-a", org_id="org-a", is_active=True)
    async def resolve(raw_key, session):
        return SimpleNamespace(id="key-a", owner_id="owner-a", org_id="org-a", scopes=scopes)
    monkeypatch.setattr(database, "get_sessionmaker", lambda: lambda: DB())
    monkeypatch.setattr(deps, "resolve_api_key", resolve)
    request = _Request(); request.headers["X-Api-Key"] = "grg_" + "a" * 40
    auth = await mcp._resolve_sse_auth(request)
    assert auth is not None and auth.scopes == expected
    assert mcp._scope_allows(auth, "chat") is (scopes is None)
