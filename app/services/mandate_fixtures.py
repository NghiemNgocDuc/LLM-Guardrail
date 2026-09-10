"""Protected fixtures — 5 ops gated by MandateFlow, with fixture_counters for crmCounter invariant.

Deterministic (no LLM) so the demo is falsifiable even when Groq 413s.
Mirrors Go fixtures in MandateFlow demo.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FixtureCounter

FIXTURES = {
    "support.list_tickets": {"risk": "medium", "desc": "List support tickets"},
    "payments.list_failures": {"risk": "high", "desc": "List payment failures"},
    "cases.lookup_subject": {"risk": "medium", "desc": "Lookup case subject"},
    "crm.resolve_customer": {"risk": "critical", "desc": "Resolve customer in CRM — provenance-gated"},
    "payments.aggregate_failures": {"risk": "medium", "desc": "Aggregate payment failures"},
}

async def _inc_counter(db: AsyncSession, org_id: str, fixture: str) -> int:
    """WAL-safe increment — SELECT FOR UPDATE then upsert, like Go _txlock=immediate."""
    res = await db.execute(
        select(FixtureCounter).where(FixtureCounter.org_id == org_id, FixtureCounter.fixture == fixture).with_for_update()
    )
    row = res.scalar_one_or_none()
    if row is None:
        row = FixtureCounter(org_id=org_id, fixture=fixture, counter=1)
        db.add(row)
        await db.flush()
        return 1
    row.counter += 1
    await db.flush()
    return row.counter

async def get_counters(db: AsyncSession, org_id: str) -> dict[str, int]:
    res = await db.execute(select(FixtureCounter).where(FixtureCounter.org_id == org_id))
    return {r.fixture: r.counter for r in res.scalars().all()}

async def invoke_fixture(db: AsyncSession, org_id: str, tool: str, inputs: dict) -> dict:
    """Only called AFTER gateway Allow — never on Deny (the invariant)."""
    if tool not in FIXTURES:
        raise ValueError(f"Unknown fixture: {tool}")
    cnt = await _inc_counter(db, org_id, tool)
    # deterministic payloads
    if tool == "support.list_tickets":
        return {"tickets": [{"id": "t1", "subject": "Login issue"}, {"id": "t2", "subject": "Billing"}], "counter": cnt}
    if tool == "payments.list_failures":
        return {"failures": [{"id": "p1", "amount": 42}], "counter": cnt}
    if tool == "cases.lookup_subject":
        handle = inputs.get("handle") or inputs.get("ref")
        return {"handle": handle, "subject": f"Subject for {handle}", "counter": cnt}
    if tool == "crm.resolve_customer":
        return {"resolved": True, "customer": inputs.get("handle"), "counter": cnt, "crmCounter": cnt}
    if tool == "payments.aggregate_failures":
        return {"aggregate": {"count": 1, "sum": 42}, "counter": cnt}
    return {"ok": True, "counter": cnt}
