"""MandateFlow gateway router — built on existing /chat + ToolApproval + MCP patterns.

Endpoints:
  POST /mandate              → create mandate
  POST /mandate/{id}/revoke  → revoke (persist-then-cancel ordering)
  POST /runs                 → create disposable Run + capability (AgentRunner)
  POST /runs/{id}/retry      → new Run + new cap, same mandate (denied again)
  POST /gateway/call          → enforce (auth cap, scope, provenance → receipt+fixture)
  GET  /runs/{id}/evidence    → 10-call receipt (the falsifiable demo)
  GET  /mandate/{id}          → mandate detail
  POST /references/mint       → server-minted provenance handle
"""
import time
import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.models import Mandate, MandateRun, MandateReceipt, Capability, ProvenanceReference
from app.services.mandate_service import (
    create_mandate, revoke_mandate, mint_capability, verify_capability,
    create_run, mint_reference, resolve_provenance_ancestry, evaluate_pinned_policy,
)
from app.services.mandate_fixtures import invoke_fixture, get_counters
import statistics

router = APIRouter(prefix="", tags=["MandateFlow"])

# ── schemas (lightweight, no extra dependency) ─────────────────────────────
from pydantic import BaseModel

class MandateCreateIn(BaseModel):
    scopes: list[str] | None = None
    ttl: int | None = None

class ReferenceMintIn(BaseModel):
    kind: str
    provenance: str | None = None
    parent_handle: str | None = None

class GatewayCallIn(BaseModel):
    tool: str
    inputs: dict[str, Any] | None = None
    handle: str | None = None  # provenance handle for the data
    run_id: str | None = None
    aud: str | None = None  # audience the capability is bound to (Microsoft 2026)
    aud_token: str | None = None  # HMAC(cap_id.aud) — replay across servers fails

class RunCreateIn(BaseModel):
    mandate_id: str
    scopes: list[str] | None = None

# ── helpers ─────────────────────────────────────────────────────────────────
def _require_org(user: CurrentUser) -> str:
    if not user.org_id:
        raise HTTPException(status_code=400, detail="User has no organization")
    return user.org_id

async def _auth_cap(db: AsyncSession, authorization: str | None) -> Capability:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer capability")
    raw = authorization[len("Bearer "):].strip()
    try:
        return await verify_capability(db, raw)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

# ── mandate ─────────────────────────────────────────────────────────────────
@router.post("/mandate", status_code=201)
async def create_mandate_ep(body: MandateCreateIn, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    org_id = _require_org(user)
    m = await create_mandate(db, org_id, user.id, body.scopes, body.ttl or 3600)
    await db.commit()
    return {"id": m.id, "org_id": m.org_id, "status": m.status, "policy_context": m.policy_context, "expires_at": m.expires_at}

@router.post("/mandate/{mandate_id}/revoke")
async def revoke_ep(mandate_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(user)
    m = await revoke_mandate(db, mandate_id)
    await db.commit()
    return {"id": m.id, "status": m.status, "revoked_at": m.revoked_at}

@router.get("/mandate/{mandate_id}")
async def get_mandate(mandate_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Mandate).where(Mandate.id == mandate_id))
    m = res.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return {"id": m.id, "status": m.status, "policy_context": m.policy_context, "created_at": m.created_at, "revoked_at": m.revoked_at}

# ── references ──────────────────────────────────────────────────────────────
@router.post("/references/mint", status_code=201)
async def mint_ref(body: ReferenceMintIn, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    org_id = _require_org(user)
    prov = body.provenance or "SUPPORT_DERIVED"
    ref = await mint_reference(db, org_id, user.id, body.kind, prov, body.parent_handle)
    await db.commit()
    return {"handle": ref.handle, "id": ref.id, "provenance": ref.provenance, "kind": ref.kind}

# ── runs — disposable Runtime ───────────────────────────────────────────────
@router.post("/runs", status_code=201)
async def create_run_ep(body: RunCreateIn, request: Request, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    from app.utils.audience import gateway_audience, sign_audience
    org_id = _require_org(user)
    run = await create_run(db, body.mandate_id, org_id, getattr(request.state, "correlation_id", None))
    cap, raw = await mint_capability(db, body.mandate_id, run.id, body.scopes)
    run.capability_id = cap.id
    await db.flush()
    await db.commit()
    aud = gateway_audience()
    return {"run_id": run.id, "runtime_id": run.runtime_id, "capability": raw, "capability_hash": cap.capability_hash, "expires_at": cap.expires_at, "scopes": cap.scopes,
            "aud": aud, "aud_token": sign_audience(cap.id, aud)}

@router.post("/runs/{run_id}/retry", status_code=201)
async def retry_run(run_id: str, request: Request, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MandateRun).where(MandateRun.id == run_id))
    prev = res.scalar_one_or_none()
    if not prev:
        raise HTTPException(status_code=404, detail="Run not found")
    # same mandate, new Run + new cap — provenance persists
    new_run = await create_run(db, prev.mandate_id, prev.org_id, getattr(request.state, "correlation_id", None))
    # carry over parent scopes
    cap_prev = None
    if prev.capability_id:
        cres = await db.execute(select(Capability).where(Capability.id == prev.capability_id))
        cap_prev = cres.scalar_one_or_none()
    scopes = cap_prev.scopes if cap_prev else None
    cap, raw = await mint_capability(db, prev.mandate_id, new_run.id, scopes)
    new_run.capability_id = cap.id
    await db.flush()
    await db.commit()
    from app.utils.audience import gateway_audience, sign_audience
    aud = gateway_audience()
    return {"run_id": new_run.id, "runtime_id": new_run.runtime_id, "mandate_id": prev.mandate_id, "capability": raw, "expires_at": cap.expires_at,
            "aud": aud, "aud_token": sign_audience(cap.id, aud)}

# ── gateway — the ONLY path to fixtures (enforcement point) ─────────────────
# Tries Go sidecar (MANDATE_GATEWAY_URL) first for speed (WAL SQLite),
# falls back to Python on timeout/error — fail-closed if Go denies.
GO_GATEWAY_URL = None  # lazy from env

async def _try_go_gateway(body: GatewayCallIn, authorization: str | None):
    import os
    url = os.getenv("MANDATE_GATEWAY_URL", "http://mandate-gateway:8182")
    if not url:
        return None
    try:
        from app.http_client import get_http_client
        client = get_http_client()
        # Go sidecar expects same Bearer + {tool, handle, inputs, run_id}
        payload = {"tool": body.tool, "handle": body.handle, "inputs": body.inputs or {}, "run_id": body.run_id}
        headers = {}
        if authorization:
            headers["Authorization"] = authorization
        # block Origin — Go rejects Origin header, Python never sends it
        resp = await client.post(f"{url.rstrip('/')}/gateway/call", json=payload, headers=headers, timeout=2.0)
        if resp.status_code < 500:
            return resp.json()
    except Exception:
        pass
    return None

@router.post("/gateway/call")
async def gateway_call(
    body: GatewayCallIn,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    # ── fast path: Go sidecar ────────────────────────────────────────────
    go_resp = await _try_go_gateway(body, authorization)
    if go_resp is not None:
        # Go already wrote its own receipt + counter (SQLite). Mirror to
        # Postgres for evidence parity so GET /runs/:id/evidence is unified.
        # We still need a Postgres receipt for the Python evidence endpoint;
        # write a shadow receipt (best-effort, never fails the call).
        try:
            cap = await _auth_cap(db, authorization)
            res = await db.execute(select(MandateRun).where(MandateRun.id == cap.run_id))
            run = res.scalar_one_or_none()
            if run:
                mres = await db.execute(select(Mandate).where(Mandate.id == cap.mandate_id))
                mand = mres.scalar_one_or_none()
                if mand:
                    shadow = MandateReceipt(
                        run_id=run.id, mandate_id=mand.id, org_id=run.org_id,
                        tool=body.tool, decision=go_resp.get("decision","ALLOW"),
                        rule_id=go_resp.get("ruleId"), reason=go_resp.get("reason"),
                        provenance_at_call=go_resp.get("provenance_at_call"),
                        latency_ms=go_resp.get("latency_ms",0),
                    )
                    db.add(shadow)
                    # mirror ALLOW to Postgres fixture counter too
                    if go_resp.get("decision") == "ALLOW":
                        await invoke_fixture(db, run.org_id, body.tool, body.inputs or {"handle": body.handle})
                    await db.commit()
        except Exception:
            pass
        return go_resp

    # ── fallback: Python (Postgres) — always available ───────────────────
    start = time.monotonic()
    cap = await _auth_cap(db, authorization)
    # Audience binding (Microsoft 2026 confused-deputy fix): when the caller
    # presents aud+aud_token they must verify; strict mode requires them.
    from app.utils.audience import enforce_audience, gateway_audience, sign_receipt, verify_audience
    if body.aud or body.aud_token:
        if not body.aud or not body.aud_token or not verify_audience(cap.id, body.aud, body.aud_token):
            raise HTTPException(status_code=403, detail="Invalid audience binding for capability")
        if body.aud != gateway_audience():
            raise HTTPException(status_code=403, detail="Capability audience mismatch")
    elif enforce_audience():
        raise HTTPException(status_code=403, detail="Audience binding required (aud + aud_token)")
    # resolve run from cap
    res = await db.execute(select(MandateRun).where(MandateRun.id == cap.run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found for capability")
    # fetch mandate for org
    mres = await db.execute(select(Mandate).where(Mandate.id == cap.mandate_id))
    mandate = mres.scalar_one_or_none()
    if not mandate or mandate.status != "active":
        raise HTTPException(status_code=403, detail="Mandate revoked")

    # scope check — like OPA static scope
    if cap.scopes and body.tool not in cap.scopes and "*" not in cap.scopes:
        decision, rule_id, reason = "DENY", "SCOPE_DENIED", f"Tool {body.tool} not in capability scope {cap.scopes}"
        provenance = None
    else:
        # provenance ancestry walk
        provenance = await resolve_provenance_ancestry(db, body.handle)
        decision, rule_id, reason = evaluate_pinned_policy(body.tool, provenance)

    latency_ms = int((time.monotonic() - start) * 1000)
    # write receipt in SAME tx as decision (MandateFlow invariant) — before fixture
    receipt = MandateReceipt(
        run_id=run.id, mandate_id=mandate.id, org_id=run.org_id,
        tool=body.tool, decision=decision, rule_id=rule_id, reason=reason,
        provenance_at_call=provenance, latency_ms=latency_ms,
    )
    db.add(receipt)
    await db.flush()

    if decision == "DENY":
        await db.commit()
        return {"decision": "DENY", "ruleId": rule_id, "reason": reason, "receipt_id": receipt.id, "tool": body.tool,
                "receipt_sig": sign_receipt(receipt.id, "DENY")}

    # ALLOW → invoke fixture (the only path) — increments fixture_counters
    try:
        result = await invoke_fixture(db, run.org_id, body.tool, body.inputs or {"handle": body.handle})
    except Exception as e:
        # record failure receipt
        receipt.decision = "DENY"
        receipt.rule_id = "FIXTURE_ERROR"
        receipt.reason = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    await db.commit()
    return {"decision": "ALLOW", "receipt_id": receipt.id, "tool": body.tool, "result": result,
            "receipt_sig": sign_receipt(receipt.id, "ALLOW")}

# ── evidence — the 10-call falsifiable demo ─────────────────────────────────
@router.get("/runs/{run_id}/evidence")
async def evidence(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MandateRun).where(MandateRun.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # all receipts for this mandate (same policy_context) ordered
    rres = await db.execute(
        select(MandateReceipt).where(MandateReceipt.mandate_id == run.mandate_id).order_by(MandateReceipt.created_at)
    )
    receipts = rres.scalars().all()
    # counters for invariant
    counters = await get_counters(db, run.org_id)
    crm_counter = counters.get("crm.resolve_customer", 0)
    return {
        "mandate_id": run.mandate_id,
        "run_id": run.id,
        "crmCounter": crm_counter,
        "counters": counters,
        "receipts": [
            {"tool": r.tool, "decision": r.decision, "ruleId": r.rule_id, "reason": r.reason}
            for r in receipts
        ],
    }

@router.get("/mandate/{mandate_id}/evidence")
async def mandate_evidence(mandate_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Mandate).where(Mandate.id == mandate_id))
    m = res.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mandate not found")
    rres = await db.execute(select(MandateReceipt).where(MandateReceipt.mandate_id == mandate_id).order_by(MandateReceipt.created_at))
    receipts = rres.scalars().all()
    # pick any run's org
    org_id = m.org_id
    counters = {}
    if org_id:
        counters = await get_counters(db, org_id)
    return {
        "mandate_id": mandate_id,
        "crmCounter": counters.get("crm.resolve_customer", 0),
        "counters": counters,
        "receipts": [{"tool": r.tool, "decision": r.decision, "ruleId": r.rule_id, "reason": r.reason} for r in receipts],
    }


# ── bench: Go vs Python head-to-head ────────────────────────────────────────
class BenchIn(BaseModel):
    iterations: int = 100
    tool: str = "crm.resolve_customer"

@router.post("/mandate/bench")
async def bench(body: BenchIn, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Run N gateway calls through Go (if up) vs Python directly, measure latency.

    Creates an isolated mandate/run/capability + two provenance handles
    (Support ALLOWED, Payment DENY) and times the pinned policy path.
    Returns avg/p50/p95 + speedup + crmCounter invariant.
    """
    org_id = _require_org(user)
    # isolated mandate for bench
    mandate = await create_mandate(db, org_id, user.id, ["*"], ttl=600)
    await db.flush()
    run = await create_run(db, mandate.id, org_id)
    cap, raw = await mint_capability(db, mandate.id, run.id, ["*"])
    run.capability_id = cap.id
    await db.flush()
    # two handles: Support (ALLOW) vs Payment (DENY)
    ref_support = await mint_reference(db, org_id, user.id, "support_case", "SUPPORT_DERIVED")
    ref_payment = await mint_reference(db, org_id, user.id, "payment_case", "PAYMENT_AGGREGATE_ONLY")
    await db.commit()

    auth = f"Bearer {raw}"
    iters = max(1, min(body.iterations, 500))

    async def time_python(handle: str) -> list[float]:
        times: list[float] = []
        for _ in range(iters):
            t0 = time.perf_counter()
            # direct Python policy eval (no DB fixture increment for pure policy bench)
            prov = await resolve_provenance_ancestry(db, handle)
            evaluate_pinned_policy(body.tool, prov)
            times.append((time.perf_counter() - t0) * 1000)
        return times

    async def time_go(handle: str) -> list[float] | None:
        import os
        url = os.getenv("MANDATE_GATEWAY_URL", "http://mandate-gateway:8182")
        if not url:
            return None
        try:
            from app.http_client import get_http_client
            client = get_http_client()
            # probe health
            try:
                h = await client.get(f"{url.rstrip('/')}/health", timeout=1.0)
                if h.status_code != 200:
                    return None
            except Exception:
                return None
            times: list[float] = []
            for _ in range(iters):
                t0 = time.perf_counter()
                resp = await client.post(
                    f"{url.rstrip('/')}/gateway/call",
                    json={"tool": body.tool, "handle": handle, "inputs": {}, "run_id": run.id},
                    headers={"Authorization": auth},
                    timeout=2.0,
                )
                _ = resp.json()  # consume
                times.append((time.perf_counter() - t0) * 1000)
            return times
        except Exception:
            return None

    def stats(times: list[float]) -> dict:
        if not times:
            return {"avg": None, "p50": None, "p95": None, "min": None, "max": None}
        s = sorted(times)
        return {
            "avg": sum(times) / len(times),
            "p50": s[len(s)//2],
            "p95": s[int(len(s)*0.95)] if len(s) > 1 else s[-1],
            "min": s[0],
            "max": s[-1],
        }

    py_support = await time_python(ref_support.handle)
    py_payment = await time_python(ref_payment.handle)
    go_support = await time_go(ref_support.handle)
    go_payment = await time_go(ref_payment.handle)

    go_available = go_support is not None
    # speedup = python_avg / go_avg (higher = Go faster)
    speedup = None
    if go_available and stats(go_support)["avg"] and stats(py_support)["avg"]:
        try:
            speedup = stats(py_support)["avg"] / stats(go_support)["avg"]
        except Exception:
            pass

    # prove crmCounter still correct after bench (DENY never increments)
    counters = await get_counters(db, org_id)

    return {
        "iterations": iters,
        "tool": body.tool,
        "go_available": go_available,
        "go_gateway_url": "http://mandate-gateway:8182" if go_available else None,
        "python": {"support": stats(py_support), "payment": stats(py_payment)},
        "go": {"support": stats(go_support) if go_support else None, "payment": stats(go_payment) if go_payment else None},
        "speedup_go_vs_python": speedup,
        "counters": counters,
        "note": "Payment DENY should not increment fixture_counters; support ALLOW does. Bench times ~policy eval (Python) vs full HTTP+WAL (Go).",
    }
