"""Tests for the GraphQL analytics layer (app/graphql.py).

Resolvers delegate 1:1 to the /analytics REST router functions, so the heavy
query semantics are covered by the REST tests; here we verify (a) auth wiring
in get_graphql_context, (b) that resolvers pass through the authenticated
user's org and map results into GraphQL types, and (c) that the schema is
read-only and never exposes full_prompt.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.graphql as graphql
from app.schemas import (
    AnalyticsDashboard, ProviderUsage, TimeSeriesPoint, TopBlockedReason,
    TopFiredRule, UsageSummary,
)


# ── Context helpers ─────────────────────────────────────────────────────────

def _request(headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(headers=headers or {})


class _SessionCtx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


def _info(user=None, org_id="org-1"):
    user = user or SimpleNamespace(id="u1", org_id=org_id, is_active=True)
    return SimpleNamespace(context={"user": user})


# ── Auth wiring ─────────────────────────────────────────────────────────────

def test_context_missing_header_raises_401():
    with pytest.raises(Exception) as exc:
        asyncio.run(graphql.get_graphql_context(_request({}), response=None))
    assert exc.value.status_code == 401


def test_context_malformed_scheme_raises_401():
    with pytest.raises(Exception) as exc:
        asyncio.run(graphql.get_graphql_context(
            _request({"authorization": "Basic dXNlcjpwYXNz"}), response=None
        ))
    assert exc.value.status_code == 401


# ── Resolver delegation (REST functions faked) ──────────────────────────────

def test_top_blocked_reasons_delegates_and_maps(monkeypatch):
    seen = {}

    async def fake_top_blocked_reasons(user, days, limit, db):
        seen["user"] = user
        seen["days"] = days
        seen["limit"] = limit
        seen["db"] = db
        return [
            TopBlockedReason(
                fired_rule="pii_detected",
                count=3,
                last_occurred_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
            )
        ]

    monkeypatch.setattr(graphql.analytics_router, "top_blocked_reasons", fake_top_blocked_reasons)
    monkeypatch.setattr(graphql, "_open_session", lambda: _SessionCtx(object()))

    rows = asyncio.run(
        graphql.Query().top_blocked_reasons(_info(org_id="org-9"), days=7, limit=10)
    )

    assert seen["days"] == 7 and seen["limit"] == 10
    assert seen["user"].org_id == "org-9"
    assert rows[0].fired_rule == "pii_detected"
    assert rows[0].count == 3
    assert rows[0].last_occurred_at == "2026-08-01T12:00:00+00:00"


def test_request_logs_maps_items_and_hides_full_prompt(monkeypatch):
    async def fake_logs(user, db, **kwargs):
        return {
            "total": 1,
            "page": 1,
            "page_size": 25,
            "items": [{
                "id": "r1", "status": "delivered", "prompt_preview": "hello",
                "full_prompt": None, "model": "llama", "backend": "groq",
                "latency_ms": 12, "input_passed": True, "output_passed": True,
                "input_block_reason": None, "output_block_reason": None,
                "fired_rule": None, "input_tokens": 5, "output_tokens": 7,
                "created_at": "2026-08-01T10:00:00+00:00", "request_id": "r1",
            }],
        }

    monkeypatch.setattr(graphql.analytics_router, "logs", fake_logs)
    monkeypatch.setattr(graphql, "_open_session", lambda: _SessionCtx(object()))

    items = asyncio.run(graphql.Query().request_logs(_info(org_id="org-1")))

    assert items[0].id == "r1"
    assert items[0].model == "llama"
    assert items[0].input_tokens == 5
    assert not hasattr(items[0], "full_prompt")


def test_false_positive_candidates_delegates(monkeypatch):
    async def fake_fp(user, days, limit, db):
        return [{
            "fired_rule": "toxic_content",
            "count": 1,
            "examples": [{
                "id": "r3", "status": "input_blocked", "prompt_preview": "bad word",
                "created_at": "2026-08-02T11:00:00+00:00",
                "positive_feedback": False, "override_hit": True,
            }],
        }]

    monkeypatch.setattr(graphql.analytics_router, "false_positive_candidates", fake_fp)
    monkeypatch.setattr(graphql, "_open_session", lambda: _SessionCtx(object()))

    rules = asyncio.run(graphql.Query().false_positive_candidates(_info(org_id="org-1")))

    assert rules[0].fired_rule == "toxic_content"
    assert rules[0].examples[0].override_hit is True
    assert rules[0].examples[0].id == "r3"


def test_dashboard_maps_all_sections(monkeypatch):
    summary = UsageSummary(
        total_requests=10, delivered=8, input_blocked=1, output_blocked=1,
        rate_limited=0, error_count=0, block_rate_pct=20.0,
        avg_latency_ms=12.5, total_tokens=100, estimated_cost_usd=0.0012,
    )

    async def fake_dashboard(user, days, db):
        return AnalyticsDashboard(
            summary=summary,
            time_series=[TimeSeriesPoint(ts="2026-08-01", total=10, delivered=8, blocked=2)],
            top_rules=[TopFiredRule(rule="pii_detected", count=1)],
            provider_usage=[ProviderUsage(backend="groq", model="llama", count=8, tokens=90)],
            recent_suspicious=[{
                "id": "r2", "status": "input_blocked", "prompt_preview": "x",
                "backend": "groq", "fired_rule": "pii_detected",
                "reason": "pii_detected", "created_at": "2026-08-01T10:00:00+00:00",
            }],
            recent_logs=[{
                "id": "r1", "status": "delivered", "prompt_preview": "hello",
                "model": "llama", "backend": "groq", "latency_ms": 12,
                "fired_rule": None, "created_at": "2026-08-01T10:00:00+00:00",
            }],
        )

    monkeypatch.setattr(graphql.analytics_router, "dashboard", fake_dashboard)
    monkeypatch.setattr(graphql, "_open_session", lambda: _SessionCtx(object()))

    data = asyncio.run(graphql.Query().dashboard(_info(org_id="org-1")))

    assert data.summary.total_requests == 10
    assert data.summary.block_rate_pct == 20.0
    assert data.time_series[0].total == 10
    assert data.top_rules[0].rule == "pii_detected"
    assert data.provider_usage[0].tokens == 90
    assert data.recent_suspicious[0].reason == "pii_detected"
    assert data.recent_logs[0].latency_ms == 12


# ── Schema shape ────────────────────────────────────────────────────────────

def test_schema_is_read_only():
    assert graphql.schema.mutation is None
    sdl = graphql.schema.as_str()
    for field in ("dashboard", "topBlockedReasons", "requestLogs", "falsePositiveCandidates"):
        assert field in sdl


def test_schema_never_exposes_full_prompt():
    sdl = graphql.schema.as_str()
    assert "fullPrompt" not in sdl
    assert "full_prompt" not in sdl
