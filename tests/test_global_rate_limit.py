"""Normal dashboard reads must not consume stricter action quotas."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import rate_limit_middleware as limits


@pytest.fixture
def client(monkeypatch):
    limits._ip_windows.clear()
    async def memory_only():
        return None
    monkeypatch.setattr(limits, "_get_redis", memory_only)
    app = FastAPI()
    app.add_middleware(limits.GlobalRateLimitMiddleware)
    @app.api_route("/{path:path}", methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
    def route(path: str):
        return {"ok": True}
    with TestClient(app) as current:
        yield current
    limits._ip_windows.clear()


def test_browsing_does_not_block_billing_reads_or_consume_checkout_quota(client):
    for _ in range(40):
        assert client.get("/analytics/dashboard").status_code == 200
    # Repeated billing visits load these four endpoints concurrently in the UI.
    for _ in range(10):
        for path in ("wallet", "plans", "purchases", "config"):
            assert client.get(f"/billing/{path}").status_code == 200
    assert client.post("/billing/checkout").status_code == 200


def test_sensitive_mutations_are_limited_and_keep_separate_group_quotas(client):
    for _ in range(30):
        assert client.post("/billing/checkout").status_code == 200
    denied = client.post("/billing/checkout")
    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "60"
    assert denied.json() == {"detail": "Too many requests — slow down."}
    assert client.get("/billing/wallet").status_code == 200
    assert client.post("/api-keys").status_code == 200
    assert client.patch("/admin/users/example").status_code == 200


@pytest.mark.parametrize("method", ["get", "head", "options"])
def test_read_and_preflight_traffic_remains_subject_to_global_flood_limit(client, method):
    request = getattr(client, method)
    for _ in range(200):
        assert request("/billing/wallet").status_code == 200
    assert request("/billing/wallet").status_code == 429


def test_sensitive_prefix_does_not_match_an_unrelated_route(client):
    for _ in range(31):
        assert client.post("/billing-information").status_code == 200
    assert client.post("/billing/checkout").status_code == 200


def test_mixed_sensitive_actions_share_their_resource_group_limit(client):
    methods = ["post", "put", "patch", "delete"]
    for index in range(30):
        assert getattr(client, methods[index % len(methods)])("/api-keys/example").status_code == 200
    assert client.delete("/api-keys/another").status_code == 429


@pytest.mark.asyncio
async def test_same_clock_redis_requests_do_not_overwrite_each_other(monkeypatch):
    class SortedSet:
        def __init__(self):
            self.members = {}
        async def evalsha(self, sha, key_count, key, now, member, limit):
            count = len(self.members)
            if count < int(limit):
                self.members[member] = float(now)
            return count
    monkeypatch.setattr(limits.time, "time", lambda: 100.0)
    monkeypatch.setattr(limits, "_global_rate_sha", "test-script")
    redis = SortedSet()
    for _ in range(30):
        await limits._check_redis(redis, "same-ip", 30)
    with pytest.raises(ValueError, match="rate_exceeded"):
        await limits._check_redis(redis, "same-ip", 30)
    assert len(redis.members) == 30
