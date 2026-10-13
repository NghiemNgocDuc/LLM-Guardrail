"""External monitoring: real outage statuses and safe, repeatable provisioning."""
import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import parse_qs
from unittest.mock import AsyncMock

import httpx
import pytest

import main as main_app
from scripts import setup_uptimerobot as setup


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("failure", [None, "error", "timeout"])
def test_health_probe(monkeypatch, method, failure):
    execute = AsyncMock()
    if failure == "error":
        execute.side_effect = RuntimeError("private connection details")

    @asynccontextmanager
    async def connect():
        if failure == "timeout":
            await asyncio.sleep(1)
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(main_app, "get_engine", lambda: SimpleNamespace(connect=connect))
    monkeypatch.setattr(main_app, "HEALTH_CHECK_TIMEOUT_SECONDS", 0.01)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_app.app),
                                     base_url="http://test") as client:
            return await client.request(method, "/health", headers={"User-Agent": "UptimeRobot"})

    response = asyncio.run(request())
    assert response.status_code == (503 if failure else 200)
    assert response.headers["cache-control"] == "no-store"
    assert "private connection details" not in response.text
    if method == "GET":
        assert response.json()["status"] == ("degraded" if failure else "ok")
    else:
        assert not response.content


def test_monitor_created_after_all_pages_checked():
    calls = []

    def handler(request):
        params = parse_qs(request.content.decode())
        calls.append((request.url.path, params))
        assert "api_key" not in request.url.query.decode()
        if request.url.path.endswith("getMonitors"):
            offset = int(params["offset"][0])
            return httpx.Response(200, json={"stat": "ok", "pagination": {"total": 2},
                                            "monitors": [{"id": offset + 1, "type": 1,
                                                          "url": f"https://other{offset}.example/health"}]})
        return httpx.Response(200, json={"stat": "ok", "monitor": {"id": 99}})

    params = {"url": "https://app.example/health", "type": 1, "http_method": 2}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert setup.ensure_monitor(client, "test-key", params) == ("created", 99)
    assert len(calls) == 3
    assert calls[-1][0].endswith("newMonitor")
    assert calls[-1][1]["http_method"] == ["2"]


def test_existing_monitor_is_reused():
    def handler(request):
        assert request.url.path.endswith("getMonitors")
        return httpx.Response(200, json={"stat": "ok", "pagination": {"total": 1},
                                        "monitors": [{"id": 42, "type": 1, "status": 2,
                                                      "url": "https://app.example/health"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert setup.ensure_monitor(client, "test-key", {"url": "https://app.example/health"}) == ("existing", 42)


@pytest.mark.parametrize("body", [{"stat": "fail", "error": {"message": "secret-key"}}, []])
def test_api_failure_does_not_expose_response(body):
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))) as client:
        with pytest.raises(RuntimeError) as exc:
            setup.api_call(client, "secret-key", "getMonitors")
    assert "secret-key" not in str(exc.value)


@pytest.mark.parametrize("url", ["", "http://app.example", "https://localhost", "https://u:p@app.example",
                                 "https://app.example?token=secret", "https://app.example/path"])
def test_invalid_monitor_url(url):
    with pytest.raises(ValueError):
        setup.health_url(url)


def test_dry_run_uses_no_network_or_key(monkeypatch, capsys):
    monkeypatch.setattr(setup, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("UPTIMEROBOT_API_KEY", raising=False)
    monkeypatch.delenv("UPTIMEROBOT_ALERT_CONTACTS", raising=False)
    monkeypatch.setattr(setup.httpx, "Client", lambda **kwargs: pytest.fail("unexpected network access"))
    assert setup.main(["--url", "https://app.example/", "--dry-run"]) == 0
    config = json.loads(capsys.readouterr().out)
    assert config["url"] == "https://app.example/health"
    assert config["interval"] == 300
    assert "api_key" not in config
