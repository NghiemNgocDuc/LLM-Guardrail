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
    org_id = _require_org(user)
    run = await create_run(db, body.mandate_id, org_id, getattr(request.state, "correlation_id", None))
    cap, raw = await mint_capability(db, body.mandate_id, run.id, body.scopes)
    run.capability_id = cap.id
    await db.flush()
    await db.commit()
    return {"run_id": run.id, "runtime_id": run.runtime_id, "capability": raw, "capability_hash": cap.capability_hash, "expires_at": cap.expires_at, "scopes": cap.scopes}

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
    return {"run_id": new_run.id, "runtime_id": new_run.runtime_id, "mandate_id": prev.mandate_id, "capability": raw, "expires_at": cap.expires_at}

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
        return {"decision": "DENY", "ruleId": rule_id, "reason": reason, "receipt_id": receipt.id, "tool": body.tool}

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
    return {"decision": "ALLOW", "receipt_id": receipt.id, "tool": body.tool, "result": result}

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
