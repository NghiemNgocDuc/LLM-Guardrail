"""Private SSE output stays buffered until the complete policy verdict."""
import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.config import get_settings
from app.models import Memory, OrgPolicy, TokenWallet
from app.routers import chat as routes
from app.schemas import ChatRequest
from app.services import memory
from app.services.llm.base import LLMStreamChunk
from guardrails.input import GuardrailResult
from guardrails.output import OutputGuardrailResult


@pytest.fixture
def stream_gateway(monkeypatch):
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", True)
    policy = SimpleNamespace(input_rules={"block_secrets": False, "block_pii": False, "block_prompt_injection": False, "block_jailbreak": False}, output_rules={"block_toxic_content": False}, topic_policy={}, compliance_rules={}, custom_rule_rego=None, llm_backend=None, llm_model=None, rate_limit_rpm=None, rate_limit_rpd=None)
    wallet = SimpleNamespace(balance_tokens=10000)
    logs = []

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def scalar_one(self):
            return self.value

        def scalars(self):
            return self

        def all(self):
            return []

    class Database:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, query):
            entity = query.column_descriptions[0]["entity"]
            assert entity in {OrgPolicy, TokenWallet, Memory}
            return Result(policy if entity is OrgPolicy else wallet if entity is TokenWallet else None)

        async def commit(self):
            pass

        async def flush(self):
            pass

        async def close(self):
            pass

    async def no_op(*args, **kwargs):
        return None

    async def require_balance(*args, **kwargs):
        return wallet

    async def recall(*args, **kwargs):
        return []

    async def log_request(**kwargs):
        logs.append(kwargs)

    monkeypatch.setattr(routes, "get_sessionmaker", lambda: Database)
    for name in ("check_prompt_dedup", "check_rate_limit", "enforce_demo_rate_limits", "deduct_tokens", "upsert_conversation"):
        monkeypatch.setattr(routes, name, no_op)
    for name in ("check_daily_budget", "enforce_demo_payload_limits", "record_daily_spend", "capture_event"):
        monkeypatch.setattr(routes, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "require_balance", require_balance)
    monkeypatch.setattr(routes, "_log_request", log_request)
    monkeypatch.setattr(memory, "recall_memories", recall)
    key = SimpleNamespace(id=str(uuid.uuid4()), owner_id=str(uuid.uuid4()), org_id=str(uuid.uuid4()), scopes=["chat"])
    request = Request({"type": "http", "method": "POST", "path": "/chat/stream", "headers": [], "client": ("127.0.0.1", 5000)})

    async def start():
        return await routes.chat_stream(ChatRequest(prompt="Summarize public documentation."), request, key, Database())

    return start, policy, key, logs


def event(chunk):
    return json.loads(chunk.split("data: ", 1)[1])


def install_stream(monkeypatch, tokens, *, finish=True, fail=False):
    async def stream(**kwargs):
        for token in tokens:
            yield LLMStreamChunk(token=token)
        if fail:
            raise RuntimeError("Local model interrupted")
        if finish:
            yield LLMStreamChunk(token="", done=True, model="private-model", backend="ollama", input_tokens=4, output_tokens=5)
    monkeypatch.setattr(routes, "stream_llm", stream)


@pytest.mark.asyncio
async def test_blocked_private_stream_emits_zero_content_tokens(stream_gateway, monkeypatch):
    start, _, _, logs = stream_gateway
    credential = "grg_" + "z" * 40
    install_stream(monkeypatch, ["Credential: ", credential[:12], credential[12:]])
    response = await start()
    events = [event(chunk) async for chunk in response.body_iterator]
    assert [item["type"] for item in events] == ["output_blocked"]
    assert events[0]["output_guard"]["reason_code"] == "secret_leakage"
    assert credential not in json.dumps(events)
    assert logs[-1]["status"] == "output_blocked"


@pytest.mark.asyncio
async def test_allowed_private_stream_releases_content_only_after_complete_guard(stream_gateway, monkeypatch):
    start, _, _, _ = stream_gateway
    text = "Public documentation. " * 60
    install_stream(monkeypatch, [text[:400], text[400:]])
    checked = []
    original = routes.OutputGuardrail.check

    def check(self, content):
        checked.append(content)
        return original(self, content)

    monkeypatch.setattr(routes.OutputGuardrail, "check", check)
    response = await start()
    events = []
    async for chunk in response.body_iterator:
        item = event(chunk)
        if item["type"] == "token":
            assert checked == [text]
        events.append(item)
    assert "".join(item["content"] for item in events if item["type"] == "token") == text
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_private_stream_delivers_sanitized_result_instead_of_original_chunks(stream_gateway, monkeypatch):
    start, _, _, _ = stream_gateway
    install_stream(monkeypatch, ["Original unreviewed output."])
    monkeypatch.setattr(routes.OutputGuardrail, "check", lambda *args: OutputGuardrailResult(allowed=True, check="Sanitizer", sanitized_output="Reviewed output."))
    response = await start()
    events = [event(chunk) async for chunk in response.body_iterator]
    assert "".join(item["content"] for item in events if item["type"] == "token") == "Reviewed output."


@pytest.mark.parametrize("finish,fail", [(False, False), (False, True)])
@pytest.mark.asyncio
async def test_interrupted_private_stream_never_releases_partial_output(stream_gateway, monkeypatch, finish, fail):
    start, _, _, logs = stream_gateway
    install_stream(monkeypatch, ["Partial unreviewed content."], finish=finish, fail=fail)
    response = await start()
    events = [event(chunk) async for chunk in response.body_iterator]
    assert [item["type"] for item in events] == ["error"]
    assert logs[-1]["status"] == "error"


@pytest.mark.asyncio
async def test_private_keepalive_does_not_cancel_slow_local_generation(stream_gateway, monkeypatch):
    start, _, _, _ = stream_gateway
    monkeypatch.setattr(routes, "_SSE_KEEPALIVE_S", 0.01)

    async def slow_stream(**kwargs):
        await asyncio.sleep(0.04)
        yield LLMStreamChunk(token="Public result.")
        yield LLMStreamChunk(token="", done=True, model="private-model", backend="ollama")

    monkeypatch.setattr(routes, "stream_llm", slow_stream)
    response = await start()
    events = [event(chunk) async for chunk in response.body_iterator]
    assert any(item["type"] == "ping" for item in events)
    assert "".join(item["content"] for item in events if item["type"] == "token") == "Public result."
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize("private", [True, False])
@pytest.mark.asyncio
async def test_stream_input_uses_workspace_rego_before_model_call(stream_gateway, monkeypatch, private):
    start, policy, key, _ = stream_gateway
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", private)
    policy.custom_rule_rego = "package guardrail\ndecision := {\"action\": \"block\", \"reason\": \"Restricted\"}"
    seen = []

    class Guard:
        def __init__(self, rules, custom_rule_rego=None, org_id=None):
            seen.append((custom_rule_rego, org_id))

        def check(self, prompt):
            return GuardrailResult(allowed=False, check="Custom policy", reason_code="rego_custom_rule", reason="Restricted")

    async def unexpected_stream(**kwargs):
        pytest.fail("A policy-blocked prompt must not reach the model")
        yield

    monkeypatch.setattr(routes, "InputGuardrail", Guard)
    monkeypatch.setattr(routes, "stream_llm", unexpected_stream)
    response = await start()
    events = [event(chunk) async for chunk in response.body_iterator]
    assert seen == [(policy.custom_rule_rego, key.org_id)]
    assert [item["type"] for item in events] == ["blocked"]


@pytest.mark.asyncio
async def test_nonprivate_stream_keeps_existing_immediate_token_behavior(stream_gateway, monkeypatch):
    start, _, _, _ = stream_gateway
    monkeypatch.setattr(get_settings(), "PRIVATE_MODE", False)
    install_stream(monkeypatch, ["First.", " Second."])
    checked = []
    original = routes.OutputGuardrail.check

    def check(self, content):
        checked.append(content)
        return original(self, content)

    monkeypatch.setattr(routes.OutputGuardrail, "check", check)
    response = await start()
    async for chunk in response.body_iterator:
        item = event(chunk)
        if item["type"] == "token":
            assert not checked
        elif item["type"] == "done":
            assert checked == ["First. Second."]
