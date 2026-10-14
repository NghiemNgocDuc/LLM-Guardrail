"""Private inference rejects remote routes before sending prompt content."""
import importlib
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

import app.config as config
import app.services.llm as llm
from app.config import Settings
from app.services.llm import ollama


def private_settings(**overrides):
    values = {
        "APP_ENV": "test", "PRIVATE_MODE": True,
        "DATABASE_URL": "", "RATE_LIMIT_REDIS_URL": "",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "OPA_URL": "http://opa:8181", "DEFAULT_MODEL": "qwen3:1.7b",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def private(monkeypatch):
    cfg = private_settings()
    monkeypatch.setattr(config, "get_settings", lambda: cfg)
    monkeypatch.setattr(llm, "settings", cfg)
    for backend in (
        "ollama", "groq", "openai", "anthropic", "gemini", "openai_compatible", "litellm",
    ):
        module = importlib.import_module(f"app.services.llm.{backend}")
        monkeypatch.setattr(module, "settings", cfg)
    llm.reset_breaker("ollama")
    yield cfg
    llm.reset_breaker("ollama")


def test_private_settings_disable_telemetry_vectors_debug_and_cloud_keys():
    cfg = private_settings(
        DEBUG=True, SENTRY_DSN="https://telemetry.invalid/1",
        POSTHOG_API_KEY="test-telemetry", PINECONE_API_KEY="test-vector",
        PINECONE_STORE_CONVERSATIONS=True, GROQ_API_KEY="test-provider",
        OPENAI_API_KEY="test-provider", DEFAULT_LLM_BACKEND="groq",
        LLM_FAILOVER_BACKENDS="openai,groq",
    )
    assert not cfg.DEBUG
    assert cfg.DEFAULT_LLM_BACKEND == "ollama"
    assert cfg.DEFAULT_MODEL == "qwen3:1.7b"
    assert not any((cfg.SENTRY_DSN, cfg.POSTHOG_API_KEY, cfg.PINECONE_API_KEY,
                    cfg.GROQ_API_KEY, cfg.OPENAI_API_KEY, cfg.LLM_FAILOVER_BACKENDS))
    assert not cfg.PINECONE_STORE_CONVERSATIONS


def test_settings_validate_configured_encryption_key_before_serving_requests():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    assert private_settings(ENCRYPTION_KEY=key).ENCRYPTION_KEY == key
    assert private_settings(ENCRYPTION_KEY="").ENCRYPTION_KEY == ""
    with pytest.raises(ValidationError, match="ENCRYPTION_KEY must be a valid Fernet key"):
        private_settings(ENCRYPTION_KEY="invalid-key")


def test_private_settings_disable_external_account_feedback_and_billing_integrations():
    names = (
        "CLERK_SECRET_KEY", "CLERK_JWKS_URL", "CLERK_JWT_KEY", "CLERK_WEBHOOK_SECRET",
        "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
        "RESEND_API_KEY", "RESEND_FROM", "FEEDBACK_RECIPIENT", "PRODUCTBRIDGE_API_KEY",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PUBLISHABLE_KEY",
    )
    cfg = private_settings(**{name: "configured-test-integration" for name in names},
                           BILLING_ENABLED=True, REQUIRE_EMAIL_VERIFICATION=True)
    assert all(getattr(cfg, name) == "" for name in names)
    assert not cfg.email_configured
    assert not cfg.BILLING_ENABLED
    assert not cfg.REQUIRE_EMAIL_VERIFICATION


@pytest.mark.parametrize("url", [
    "https://api.example.com", "http://127.0.0.1.example.com:11434",
    "http://localhost@api.example.com", "http://name:secret@localhost:11434",
    "http://localhost:11434/?token=secret", "http://localhost:11434/proxy",
    "http://localhost:11434/#token", "file:///tmp/ollama",
    "http://10.0.0.1:11434", "http://localhost:bad", "http://[::1",
])
def test_private_settings_reject_unsafe_ollama_endpoints(url):
    with pytest.raises(ValidationError, match="PRIVATE_MODE requires OLLAMA_BASE_URL"):
        private_settings(OLLAMA_BASE_URL=url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434", "http://localhost:11434/",
    "http://[::1]:11434", "http://ollama:11434",
])
def test_private_settings_accept_loopback_or_internal_ollama(url):
    assert private_settings(OLLAMA_BASE_URL=url).OLLAMA_BASE_URL == url.rstrip("/")


@pytest.mark.parametrize("field,value", [
    ("DATABASE_URL", "postgresql+asyncpg://user:pass@db.example.com/app"),
    ("DATABASE_URL", "postgresql+asyncpg://user:pass@db/app?host=outside.example.com"),
    ("DATABASE_URL", "sqlitecloud://outside.example.com/app"),
    ("RATE_LIMIT_REDIS_URL", "redis://redis.example.com:6379/0"),
    ("RATE_LIMIT_REDIS_URL", "redis://redis:6379/0?host=outside.example.com"),
    ("OPA_URL", "https://opa.example.com"),
    ("OPA_URL", "http://user:pass@opa:8181"),
])
def test_private_settings_reject_remote_state_or_policy_services(field, value):
    with pytest.raises(ValidationError, match="PRIVATE_MODE requires"):
        private_settings(**{field: value})


def test_private_settings_allow_internal_state_authentication_and_local_sqlite():
    cfg = private_settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@db/app",
        RATE_LIMIT_REDIS_URL="redis://:pass@redis:6379/0",
    )
    assert cfg.DATABASE_URL.endswith("@db/app")
    assert private_settings(DATABASE_URL="sqlite+aiosqlite:///:memory:").PRIVATE_MODE


@pytest.mark.parametrize("backend", ["groq", "openai", "anthropic", "gemini", "litellm", "mock"])
@pytest.mark.parametrize("source", ["request", "organization"])
def test_private_router_rejects_remote_or_test_overrides(private, backend, source):
    args = {"request_backend": None, "org_backend": None, "request_model": None, "org_model": None}
    args["request_backend" if source == "request" else "org_backend"] = backend
    with pytest.raises(ValueError, match="only the self-hosted Ollama"):
        llm.resolve_adapter(**args)


@pytest.mark.parametrize("model", ["qwen3:4b", "qwen3:cloud", "local-cloud-alias"])
def test_private_router_pins_the_selected_local_model(private, model):
    with pytest.raises(ValueError, match="PRIVATE_MODE"):
        llm.resolve_adapter(None, None, model, None)


@pytest.mark.parametrize("fallbacks", [["groq"], ["openai/gpt-4o"], ["ollama/qwen3:cloud"]])
@pytest.mark.asyncio
async def test_private_fallback_is_rejected_before_primary_inference(private, monkeypatch, fallbacks):
    calls = []

    class MustNotRun:
        async def complete(self, *args):
            calls.append(args)
            raise AssertionError("Forbidden configuration must fail before inference")

    monkeypatch.setitem(llm._ADAPTERS, "ollama", MustNotRun())
    with pytest.raises(ValueError, match="PRIVATE_MODE"):
        await llm.call_llm("private input", 0, 8, fallbacks=fallbacks)
    assert calls == []


@pytest.mark.asyncio
async def test_private_stream_rejects_remote_fallback_before_first_token(private):
    with pytest.raises(ValueError, match="PRIVATE_MODE"):
        _ = [chunk async for chunk in llm.stream_llm("private input", 0, 8, fallbacks=["groq"])]


def test_private_available_backends_hide_hosted_providers(private):
    assert llm.get_available_backends() == ["ollama"]


def test_global_model_is_honored_only_for_its_configured_backend(monkeypatch):
    cfg = SimpleNamespace(
        PRIVATE_MODE=False, DEFAULT_LLM_BACKEND="ollama", DEFAULT_MODEL="qwen3:1.7b",
    )
    monkeypatch.setattr(llm, "settings", cfg)
    assert llm.resolve_adapter(None, None, None, None)[2] == "qwen3:1.7b"
    assert llm.resolve_adapter("openai", None, None, None)[2] == "gpt-4o"
    assert llm.resolve_adapter(None, "ollama", None, "qwen3:4b")[2] == "qwen3:4b"
    assert llm.resolve_adapter(None, "ollama", "qwen3:0.6b", "qwen3:4b")[2] == "qwen3:0.6b"


@pytest.mark.parametrize("backend", [
    "groq", "openai", "anthropic", "gemini", "openai_compatible", "litellm", "xai", "mock",
])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.asyncio
async def test_private_direct_adapter_call_cannot_use_provider_keys(private, monkeypatch, backend, stream):
    # Even restored credentials and SDK environment variables cannot authorize
    # hosted inference, including callers that bypass resolve_adapter().
    private.GROQ_API_KEY = "test-provider"
    private.OPENAI_API_KEY = "test-provider"
    private.ANTHROPIC_API_KEY = "test-provider"
    private.GEMINI_API_KEY = "test-provider"
    private.XAI_API_KEY = "test-provider"
    monkeypatch.setenv("GROQ_API_KEY", "test-provider")
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider")
    for name in ("groq", "openai", "anthropic", "gemini", "openai_compatible"):
        module = importlib.import_module(f"app.services.llm.{name}")
        monkeypatch.setattr(module, "get_http_client", lambda: pytest.fail("Hosted HTTP client accessed"))
    adapter = llm._ADAPTERS[backend]
    with pytest.raises(ValueError, match="PRIVATE_MODE permits only"):
        if stream:
            _ = [chunk async for chunk in adapter.stream("private input", "anything", 0, 8)]
        else:
            await adapter.complete("private input", "anything", 0, 8)


@pytest.mark.parametrize("case", ["cloud_enabled", "unknown_status", "remote_alias", "remote_model_alias", "missing_model", "timeout"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.asyncio
async def test_private_ollama_preflight_failure_never_receives_prompt(private, monkeypatch, case, stream):
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/api/status":
            if case == "timeout":
                raise httpx.ReadTimeout("local status unavailable", request=request)
            return httpx.Response(200, json={"cloud": {"disabled": case != "cloud_enabled"}} if case != "unknown_status" else {})
        if request.url.path == "/api/show":
            if case == "remote_model_alias":
                return httpx.Response(200, json={"remote_model": "hosted-model"})
            return httpx.Response(404 if case == "missing_model" else 200,
                                  json={"remote_host": "https://ollama.com"} if case == "remote_alias" else {"details": {"format": "gguf"}})
        raise AssertionError("Prompt must not be submitted after a failed private preflight")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as client:
        monkeypatch.setattr(ollama, "get_http_client", lambda: client)
        with pytest.raises((ValueError, httpx.HTTPError)):
            if stream:
                _ = [chunk async for chunk in ollama.OllamaAdapter().stream("private input", private.DEFAULT_MODEL, 0, 8)]
            else:
                await ollama.OllamaAdapter().complete("private input", private.DEFAULT_MODEL, 0, 8)
    assert all(b"private input" not in request.content for request in requests)


@pytest.mark.asyncio
async def test_private_ollama_completion_uses_only_verified_local_runtime(private, monkeypatch):
    paths = []

    def respond(request):
        assert request.url.host == "127.0.0.1"
        paths.append(request.url.path)
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True}})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        payload = json.loads(request.content)
        assert payload["model"] == private.DEFAULT_MODEL
        assert payload["think"] is False
        assert payload["messages"][0]["content"] == "private input"
        return httpx.Response(200, json={"message": {"content": "local result"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as client:
        monkeypatch.setattr(ollama, "get_http_client", lambda: client)
        response = await llm.call_llm("private input", 0, 8)
    assert response.text == "local result"
    assert paths == ["/api/status", "/api/show", "/api/chat"]


@pytest.mark.parametrize("body", [
    b'{"message":{"content":"partial"},"done":false}\n',
    b'{"error":"private provider details must stay out of error text"}\n',
    b'not-json\n',
])
@pytest.mark.asyncio
async def test_private_ollama_never_treats_failed_or_truncated_stream_as_completed(private, monkeypatch, body):
    def respond(request):
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True}})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        return httpx.Response(200, content=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as client:
        monkeypatch.setattr(ollama, "get_http_client", lambda: client)
        with pytest.raises(ValueError, match="Private Ollama") as error:
            _ = [chunk async for chunk in llm.stream_llm("private input", 0, 8)]
    assert "private provider details" not in str(error.value)


@pytest.mark.asyncio
async def test_private_ollama_stream_returns_text_and_final_usage(private, monkeypatch):
    def respond(request):
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True}})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        assert json.loads(request.content)["think"] is False
        return httpx.Response(200, content=b'{"message":{"content":"local"},"done":false}\n{"message":{"content":" result"},"done":true,"prompt_eval_count":2,"eval_count":1}\n')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as client:
        monkeypatch.setattr(ollama, "get_http_client", lambda: client)
        chunks = [chunk async for chunk in llm.stream_llm("private input", 0, 8)]
    assert "".join(chunk.token for chunk in chunks) == "local result"
    assert chunks[-1].done and chunks[-1].input_tokens == 2 and chunks[-1].output_tokens == 1


def test_private_direct_groq_judge_stays_offline(private, monkeypatch):
    from guardrails import semantic
    monkeypatch.setenv("GROQ_API_KEY", "test-provider" * 3)
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: pytest.fail("Hosted judge accessed HTTP"))
    assert semantic._groq_implicit_judge("private input") == (False, "")


def test_private_implicit_judge_stays_offline_even_with_environment_keys(private, monkeypatch):
    from guardrails import semantic
    monkeypatch.setenv("GROQ_API_KEY", "test-provider" * 3)
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider" * 3)
    monkeypatch.setattr(semantic, "_groq_implicit_judge", lambda _: pytest.fail("Hosted judge invoked"))
    assert semantic.is_implicit("An ordinary project update.", use_llm=True) == (False, "")
    assert semantic.is_implicit("The only female engineer on the Platform team.", use_llm=True)[0]


@pytest.mark.asyncio
async def test_private_vectors_cannot_reuse_an_existing_remote_connection(private, monkeypatch):
    from app.services import vectorstore
    monkeypatch.setattr(vectorstore, "get_settings", lambda: private)
    monkeypatch.setattr(vectorstore, "_pinecone_initialized", True)
    monkeypatch.setattr(vectorstore, "_index", lambda: pytest.fail("Remote vector index accessed"))
    monkeypatch.setattr(vectorstore, "_get_embedding_model", lambda: pytest.fail("Remote persistence path encoded content"))
    await vectorstore.upsert_memory("m1", "private input")
    await vectorstore.upsert_conversation("s1", "private input", "private output", "input_blocked")
    assert await vectorstore.query_memories("private input") == []
    assert await vectorstore.semantic_similarity("private input") == []
    vectorstore.init()
    assert not vectorstore._pinecone_initialized


def test_private_database_never_echoes_sql_parameters(private, monkeypatch):
    from app import database
    private.DEBUG = True  # Defense in depth if a runtime caller changes it.
    private.DATABASE_URL = "postgresql+asyncpg://user:pass@db/app"
    options = {}
    monkeypatch.setattr(database, "settings", private)
    monkeypatch.setattr(database, "engine", None)
    def create_engine(url, **kwargs):
        options.update(kwargs)
        return object()
    monkeypatch.setattr(database, "create_async_engine", create_engine)
    database.get_engine()
    assert options["echo"] is False
    assert options["hide_parameters"] is True


def test_private_http_client_ignores_environment_proxies(private, monkeypatch):
    from app import http_client
    options = {}
    monkeypatch.setattr(http_client, "get_settings", lambda: private)
    monkeypatch.setattr(http_client, "_http_client", None)
    def create_client(**kwargs):
        options.update(kwargs)
        return object()
    monkeypatch.setattr(http_client.httpx, "AsyncClient", create_client)
    http_client.get_http_client()
    assert options["trust_env"] is False
    assert options["follow_redirects"] is False
