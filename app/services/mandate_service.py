"""Mandate + Capability + Provenance — Python port of Go MandateFlow sidecar.

Security: SHA-256 hash only, ConstantTimeCompare (hmac.compare_digest),
attenuation child = parent ∩ requested, short-lived caps.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Capability, Mandate, MandateRun, ProvenanceReference

# ── constants ───────────────────────────────────────────────────────────────
CAP_TTL_SECONDS = 300  # 5 min per-Run capability
MANDATE_TTL_SECONDS = 3600
PINNED_RULE_ID = "NO_PAYMENT_REIDENTIFICATION"
PINNED_REASON = "Payment-derived references are aggregate-only and cannot be resolved through CRM"

# provenance taxonomy
SUPPORT_DERIVED = "SUPPORT_DERIVED"
PAYMENT_AGGREGATE_ONLY = "PAYMENT_AGGREGATE_ONLY"
PAYMENT_DERIVED = "PAYMENT_DERIVED"

# ── helpers ─────────────────────────────────────────────────────────────────
def _hash_cap(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())

def attenuate(parent_scopes: list[str], requested: list[str]) -> list[str]:
    """child = parent ∩ requested — delegation attenuation."""
    p = set(parent_scopes or [])
    r = set(requested or [])
    if not r:
        return list(p)
    return sorted(p & r) if p else sorted(r)

def _provenance_for_tool(tool: str, current_ref: ProvenanceReference | None) -> str | None:
    if current_ref:
        return current_ref.provenance
    # mint-time mapping
    if tool in ("support.list_tickets",):
        return SUPPORT_DERIVED
    if tool in ("payments.aggregate_failures", "payments.list_failures"):
        return PAYMENT_AGGREGATE_ONLY
    return None

async def resolve_provenance_ancestry(db: AsyncSession, handle: str | None) -> str | None:
    if not handle:
        return None
    res = await db.execute(select(ProvenanceReference).where(ProvenanceReference.handle == handle))
    ref = res.scalar_one_or_none()
    if not ref:
        return None
    # walk parents — if any ancestor is PAYMENT_AGGREGATE_ONLY, taint persists
    cur = ref
    while cur:
        if cur.provenance == PAYMENT_AGGREGATE_ONLY:
            return PAYMENT_AGGREGATE_ONLY
        if cur.parent_id:
            res = await db.execute(select(ProvenanceReference).where(ProvenanceReference.id == cur.parent_id))
            cur = res.scalar_one_or_none()
        else:
            break
    return ref.provenance

def evaluate_pinned_policy(tool: str, provenance: str | None) -> tuple[str, str | None, str | None]:
    """Returns (decision, rule_id, reason). Structural DENY for PAYMENT→CRM."""
    if tool == "crm.resolve_customer" and provenance == PAYMENT_AGGREGATE_ONLY:
        return "DENY", PINNED_RULE_ID, PINNED_REASON
    return "ALLOW", None, None

# ── mandate lifecycle ───────────────────────────────────────────────────────
async def create_mandate(db: AsyncSession, org_id: str, owner_id: str, scopes: list[str] | None = None, ttl: int = MANDATE_TTL_SECONDS) -> Mandate:
    m = Mandate(
        org_id=org_id, owner_id=owner_id,
        status="active",
        policy_context={"scopes": scopes or [], "pinned_rule": PINNED_RULE_ID},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
    )
    db.add(m)
    await db.flush()
    return m

async def revoke_mandate(db: AsyncSession, mandate_id: str) -> Mandate:
    """Persist revocation BEFORE cancelling Runtime — ordering invariant."""
    res = await db.execute(select(Mandate).where(Mandate.id == mandate_id).with_for_update())
    m = res.scalar_one_or_none()
    if not m:
        raise ValueError("Mandate not found")
    m.status = "revoked"
    m.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return m

async def mint_capability(db: AsyncSession, mandate_id: str, run_id: str, requested_scopes: list[str] | None = None) -> tuple[Capability, str]:
    res = await db.execute(select(Mandate).where(Mandate.id == mandate_id).with_for_update())
    m = res.scalar_one_or_none()
    if not m or m.status != "active":
        raise ValueError("Mandate not active")
    if m.expires_at and m.expires_at < datetime.now(timezone.utc):
        raise ValueError("Mandate expired")
    parent_scopes = (m.policy_context or {}).get("scopes", [])
    scopes = attenuate(parent_scopes, requested_scopes or [])
    raw = "cap_" + secrets.token_urlsafe(32)
    h = _hash_cap(raw)
    cap = Capability(
        mandate_id=mandate_id, run_id=run_id,
        capability_hash=h, scopes=scopes,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=CAP_TTL_SECONDS),
    )
    db.add(cap)
    await db.flush()
    return cap, raw

async def verify_capability(db: AsyncSession, raw: str) -> Capability:
    h = _hash_cap(raw)
    # constant-time compare over candidates (avoid ==)
    res = await db.execute(select(Capability).where(Capability.expires_at > datetime.now(timezone.utc)))
    for cap in res.scalars().all():
        if _constant_time_eq(cap.capability_hash, h):
            # also check mandate still active
            mres = await db.execute(select(Mandate).where(Mandate.id == cap.mandate_id))
            m = mres.scalar_one_or_none()
            if not m or m.status != "active":
                raise ValueError("Mandate revoked")
            return cap
    raise ValueError("Invalid or expired capability")

async def mint_reference(db: AsyncSession, org_id: str, owner_id: str, kind: str, provenance: str, parent_handle: str | None = None) -> ProvenanceReference:
    parent_id = None
    if parent_handle:
        res = await db.execute(select(ProvenanceReference).where(ProvenanceReference.handle == parent_handle))
        parent = res.scalar_one_or_none()
        if parent:
            parent_id = parent.id
            # inherit taint: Payment parent → child stays aggregate-only
            if parent.provenance == PAYMENT_AGGREGATE_ONLY:
                provenance = PAYMENT_AGGREGATE_ONLY
    handle = f"ref_{uuid.uuid4().hex[:16]}"
    ref = ProvenanceReference(
        org_id=org_id, owner_id=owner_id, kind=kind,
        provenance=provenance, parent_id=parent_id, handle=handle,
    )
    db.add(ref)
    await db.flush()
    return ref

async def create_run(db: AsyncSession, mandate_id: str, org_id: str, correlation_id: str | None = None) -> MandateRun:
    run = MandateRun(
        mandate_id=mandate_id, org_id=org_id,
        status="running", runtime_id=f"rt_{uuid.uuid4().hex[:8]}",
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
    db.add(run)
    await db.flush()
    return run
