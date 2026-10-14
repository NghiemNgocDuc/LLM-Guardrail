"""Private deployment boundaries beyond the model adapter."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.responses import Response

from app import database, http_client, mcp_server
from app.config import get_settings
from app.routers import chat, mandate, policy
from app.schemas import PolicyUpdate
from app.services.private_audit import PRIVATE_PREVIEW
from guardrails import opa


@pytest.fixture
def private_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", True)
    monkeypatch.setattr(get_settings(), "DEFAULT_MODEL", "qwen3:1.7b")


@pytest.mark.asyncio
async def test_private_webhook_never_resolves_destination_or_sends_evidence(monkeypatch, private_mode):
    validate = AsyncMock(side_effect=AssertionError("No DNS or webhook calls in private mode"))
    monkeypatch.setattr(chat, "validate_webhook_url_resolved", validate)
    monkeypatch.setattr(chat, "get_http_client", lambda: pytest.fail("No outbound client"))
    await chat._fire_webhook("https://hooks.example.test", {"prompt_preview": "confidential evidence"}, "secret")
    validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_tool_calls_ignore_remote_sidecar_environment(monkeypatch, private_mode):
    monkeypatch.setenv("MANDATE_GATEWAY_URL", "https://remote.example.test")
    monkeypatch.setattr(http_client, "get_http_client", lambda: pytest.fail("Private tools must run locally"))
    result = await mandate._try_go_gateway(mandate.GatewayCallIn(tool="crm.resolve_customer", inputs={"note": "Private customer data"}), "Bearer confidential-capability")
    assert result is None


@pytest.mark.asyncio
async def test_private_mcp_audit_omits_non_pii_source_text(monkeypatch, private_mode):
    rows = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def add(self, row):
            rows.append(row)

        async def commit(self):
            pass

    monkeypatch.setattr(database, "get_sessionmaker", lambda: Session)
    auth = mcp_server.MCPAuthContext(key_id="key", owner_id="owner", org_id="org", scopes=["skills:read"], is_authenticated=True)
    await mcp_server._audit_log(auth, "scan_skill", {"content": "Confidential product codename Moonlight"}, "input_blocked")
    assert len(rows) == 1
    assert rows[0].prompt_preview == PRIVATE_PREVIEW
    assert rows[0].full_prompt is None
    assert "Moonlight" not in json.dumps({"preview": rows[0].prompt_preview, "reason": rows[0].output_block_reason})
    assert json.loads(mcp_server.get_default_policy())["available_backends"] == ["ollama"]


def test_private_opa_does_not_inherit_system_proxy(monkeypatch, private_mode):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(opa, "_CLIENT", None)
    monkeypatch.setattr(opa.httpx, "Client", client)
    monkeypatch.setenv("HTTP_PROXY", "http://untrusted.example.test:8080")
    opa._client()
    assert captured["trust_env"] is False


@pytest.mark.asyncio
async def test_private_html_blocks_external_scripts_fonts_and_connections(monkeypatch, private_mode):
    import main

    async def next_response(request):
        return Response("<html>Private dashboard</html>", media_type="text/html")

    request = SimpleNamespace(state=SimpleNamespace(), headers={})
    response = await main.add_security_headers(request, next_response)
    csp = response.headers["Content-Security-Policy"]
    assert "connect-src 'self'" in csp
    assert "font-src 'self'" in csp and "script-src 'self'" in csp
    assert "https:" not in csp and "*" not in csp
    assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"llm_backend": "groq"}, {"llm_backend": "ollama", "llm_model": "another-local-model"}])
async def test_private_policy_rejects_cloud_or_unconfigured_routing_before_database_write(payload, private_mode):
    user = SimpleNamespace(is_admin=True, org_id="org")
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("No writes or reads for rejected route")))
    with pytest.raises(HTTPException) as error:
        await policy.update_policy(PolicyUpdate(**payload), user, db)
    assert error.value.status_code == 422
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_null_routing_removes_legacy_cloud_override(private_mode):
    row = SimpleNamespace(id="policy", org_id="org", version=1, input_rules={}, output_rules={}, topic_policy={}, compliance_rules={}, llm_backend="groq", llm_model="legacy-model", tier="standard")
    added = []
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: row)), add=added.append, flush=AsyncMock())
    user = SimpleNamespace(id="owner", is_admin=True, org_id="org")
    await policy.update_policy(PolicyUpdate(llm_backend=None, llm_model=None), user, db)
    assert row.llm_backend is None and row.llm_model is None
    assert added[0].llm_backend == "groq" and row.version == 2
