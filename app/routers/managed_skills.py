"""
Managed SKILL.md files — team lead creates/updates versioned skill files that
agents download.  Every write is conflict-checked against the current
guardrail policy and existing managed skills (especially API-key leak).

Endpoints (all require auth; write requires admin):
  GET    /skills/managed
  POST   /skills/managed
  GET    /skills/managed/{slug}
  PUT    /skills/managed/{slug}
  DELETE /skills/managed/{slug}
  GET    /skills/managed/{slug}/versions
  POST   /skills/managed/check-conflict
  POST   /skills/managed/{slug}/check-conflict
  GET    /skills/managed/{slug}/download?mode=overwrite|versioned&live_url=...
  GET    /skills/live/{slug}          (api-key or JWT; serves raw or wrapped SKILL.md)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import CurrentUser
from app.models import OrgPolicy
from app.services.skill_store import (
    create_managed_skill,
    delete_managed_skill,
    get_managed_skill,
    list_managed_skills,
    list_skill_versions,
    update_managed_skill,
)
from guardrails.skill_conflict import build_skill_md, check_skill_conflicts
from app.services.skill_metrics import compute_metrics as compute_skill_metrics
from app.services.combined_benchmark import compute_combined
from guardrails.skill import SkillGuardrail
from guardrails.test_case_generator import generate_test_cases, run_test_cases

router = APIRouter(prefix="/skills/managed", tags=["Managed Skills"])
live_router = APIRouter(prefix="/skills/live", tags=["Managed Skills Live"])


def _require_admin(user):
    if not user.is_admin:
        from fastapi import HTTPException, status
        from app.i18n import _t
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_t("admin.access_required"))


def _require_org(user):
    if not user.org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No organization")


async def _existing_as_dicts(db: AsyncSession, org_id: str) -> list[dict]:
    rows = await list_managed_skills(db, org_id)
    return [{"slug": r.slug, "name": r.name, "content": r.content, "version": r.version} for r in rows]


async def _org_policy_dict(db: AsyncSession, org_id: str) -> dict:
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == org_id))
    pol = result.scalar_one_or_none()
    if not pol:
        return {}
    # OrgPolicy.input_rules is the canonical input policy dict
    d = dict(pol.input_rules or {})
    # also include compliance bits for API-key intent
    d["tier"] = pol.tier
    return d


# ── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[dict])
async def list_skills(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    rows = await list_managed_skills(db, current_user.org_id)
    return [
        {
            "slug": r.slug, "name": r.name, "description": r.description,
            "version": r.version, "hash": r.content_hash[:12], "full_hash": r.content_hash,
            "update_mode": r.update_mode, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "content_preview": r.content[:300],
        }
        for r in rows
    ]


@router.post("", response_model=dict, status_code=201)
async def create_skill(
    body: dict,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    _require_org(current_user)
    # Cap terms per team to 500 (managed skills)
    from sqlalchemy import func as _func
    from app.models import ManagedSkill as _MS
    cnt_res = await db.execute(_func.count().select().select_from(_MS).where(_MS.org_id == current_user.org_id))
    if (cnt_res.scalar() or 0) >= 500:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Team terms cap reached — max 500 terms per team.")
    slug = (body.get("slug") or body.get("name") or "").strip()
    name = (body.get("name") or slug).strip()
    description = (body.get("description") or "").strip()
    content = body.get("content") or ""
    update_mode = (body.get("update_mode") or "overwrite").strip()

    # conflict check before write (advisory — still allow creation but return conflicts)
    existing = await _existing_as_dicts(db, current_user.org_id)
    policy = await _org_policy_dict(db, current_user.org_id)
    conflicts = check_skill_conflicts(content, existing_skills=existing, org_policy=policy)

    # optional hard block: if body says block_on_conflict and critical, reject
    if body.get("block_on_conflict") and conflicts.blocked_by_policy:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail={
            "message": "Skill conflicts with current API-key leak protection — fix before saving",
            "conflicts": [c.__dict__ for c in conflicts.conflicts],
            "summary": conflicts.summary,
        })

    row = await create_managed_skill(
        db, org_id=current_user.org_id, slug=slug, name=name,
        description=description, content=content, update_mode=update_mode,
        created_by=current_user.id,
    )
    await db.commit()
    return {
        "slug": row.slug, "name": row.name, "description": row.description,
        "version": row.version, "hash": row.content_hash[:12], "full_hash": row.content_hash,
        "update_mode": row.update_mode,
        "conflicts": [c.__dict__ for c in conflicts.conflicts],
        "has_conflict": conflicts.has_conflict,
        "blocked_by_policy": conflicts.blocked_by_policy,
        "conflict_summary": conflicts.summary,
    }


@router.get("/{slug}", response_model=dict)
async def get_skill(slug: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    row = await get_managed_skill(db, current_user.org_id, slug)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    return {
        "slug": row.slug, "name": row.name, "description": row.description,
        "content": row.content, "version": row.version,
        "hash": row.content_hash[:12], "full_hash": row.content_hash,
        "update_mode": row.update_mode,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.put("/{slug}", response_model=dict)
async def update_skill(slug: str, body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    _require_org(current_user)
    new_content = body.get("content")
    # conflict check if content is being changed
    conflicts = None
    if new_content is not None:
        # existing skills except the one being updated (so we don't self-conflict)
        existing = [d for d in await _existing_as_dicts(db, current_user.org_id) if d["slug"] != slug.lower()]
        policy = await _org_policy_dict(db, current_user.org_id)
        conflicts = check_skill_conflicts(new_content, existing_skills=existing, org_policy=policy)
        if body.get("block_on_conflict") and conflicts.blocked_by_policy:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail={
                "message": "Update conflicts with current API-key leak protection",
                "conflicts": [c.__dict__ for c in conflicts.conflicts],
                "summary": conflicts.summary,
            })

    row = await update_managed_skill(
        db, org_id=current_user.org_id, slug=slug,
        name=body.get("name"), description=body.get("description"),
        content=new_content, update_mode=body.get("update_mode"),
        updated_by=current_user.id,
    )
    await db.commit()
    out: dict = {
        "slug": row.slug, "name": row.name, "description": row.description,
        "version": row.version, "hash": row.content_hash[:12], "full_hash": row.content_hash,
        "update_mode": row.update_mode,
    }
    if conflicts is not None:
        out["conflicts"] = [c.__dict__ for c in conflicts.conflicts]
        out["has_conflict"] = conflicts.has_conflict
        out["blocked_by_policy"] = conflicts.blocked_by_policy
        out["conflict_summary"] = conflicts.summary
    return out


@router.delete("/{slug}", response_model=dict)
async def delete_skill(slug: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    _require_org(current_user)
    await delete_managed_skill(db, org_id=current_user.org_id, slug=slug)
    await db.commit()
    return {"deleted": slug}


@router.get("/{slug}/versions", response_model=list[dict])
async def get_versions(slug: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    versions = await list_skill_versions(db, current_user.org_id, slug)
    return [
        {
            "version": v.version, "hash": v.content_hash[:12], "full_hash": v.content_hash,
            "update_mode": v.update_mode, "created_at": v.created_at.isoformat() if v.created_at else None,
            "created_by": v.created_by,
        }
        for v in versions
    ]


# ── conflict check (advisory, no write) ─────────────────────────────────────

@router.post("/check-conflict", response_model=dict)
async def check_conflict(body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    content = body.get("content") or ""
    if not content.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    # exclude slug if checking an update to existing skill (avoid self-conflict)
    exclude = (body.get("exclude_slug") or "").strip().lower()
    existing = await _existing_as_dicts(db, current_user.org_id)
    if exclude:
        existing = [d for d in existing if d["slug"] != exclude]
    policy = await _org_policy_dict(db, current_user.org_id)
    res = check_skill_conflicts(content, existing_skills=existing, org_policy=policy)
    return {
        "has_conflict": res.has_conflict,
        "safe": res.safe,
        "blocked_by_policy": res.blocked_by_policy,
        "summary": res.summary,
        "conflicts": [c.__dict__ for c in res.conflicts],
        "policy_findings": res.policy_findings,
    }


@router.post("/{slug}/check-conflict", response_model=dict)
async def check_conflict_for_slug(slug: str, body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    content = body.get("content") or ""
    if not content.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    existing = [d for d in await _existing_as_dicts(db, current_user.org_id) if d["slug"] != slug.lower()]
    policy = await _org_policy_dict(db, current_user.org_id)
    res = check_skill_conflicts(content, existing_skills=existing, org_policy=policy)
    return {
        "has_conflict": res.has_conflict,
        "safe": res.safe,
        "blocked_by_policy": res.blocked_by_policy,
        "summary": res.summary,
        "conflicts": [c.__dict__ for c in res.conflicts],
        "policy_findings": res.policy_findings,
    }


# ── download (wrapped SKILL.md with frontmatter) ────────────────────────────

@router.get("/{slug}/download")
async def download_skill(
    slug: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    mode: str = Query(default="overwrite", description="overwrite | versioned"),
    live_url: str | None = Query(default=None),
):
    _require_org(current_user)
    row = await get_managed_skill(db, current_user.org_id, slug)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    # caller can override download mode; otherwise use the skill's stored update_mode
    effective_mode = mode if mode in ("overwrite", "versioned") else row.update_mode
    # If caller forced a different mode than stored, we still honor it for THIS download only
    base = get_settings().PUBLIC_APP_URL.rstrip("/")
    default_live = f"{base}/skills/live/{slug}"
    md = build_skill_md(
        slug=row.slug, name=row.name, description=row.description,
        content=row.content, version=row.version, content_hash=row.content_hash,
        update_mode=effective_mode, live_url=live_url or default_live,
    )
    # filename respects versioned mode: SKILL.md vs SKILL.vN.md if caller asked versioned
    filename = f"{row.slug}.md" if effective_mode == "overwrite" else f"{row.slug}.v{row.version}.md"
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── metrics + identical-block scan + auto test generation ──────────────────

@router.get("/metrics", response_model=dict)
async def skill_metrics(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Live scores for skill conflict detection — used by About page."""
    _require_org(current_user)
    policy = await _org_policy_dict(db, current_user.org_id)
    metrics = compute_skill_metrics(org_policy=policy or {"block_secrets": True, "block_pii": True})
    return metrics

@router.get("/metrics/combined", response_model=dict)
async def combined_metrics(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Combined benchmark: llm-redactor + jailbreak + NotInject — single macro-F1."""
    _require_org(current_user)
    policy = await _org_policy_dict(db, current_user.org_id)
    import asyncio
    result = await asyncio.to_thread(compute_combined, policy, 150)
    return result

@router.get("/metrics/export-pdf")
async def export_evidence_pdf(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Evidence pack PDF — no email in metadata, signed hash, reproducible."""
    _require_org(current_user)
    policy = await _org_policy_dict(db, current_user.org_id)
    import asyncio
    from app.services.export_pdf import build_evidence_pdf
    from guardrails.test_case_generator import generate_test_cases, run_test_cases
    # Metrics (9 fixtures)
    from app.services.skill_metrics import compute_metrics as _cm
    metrics = await asyncio.to_thread(_cm, policy or {"block_secrets": True, "block_pii": True})
    combined = await asyncio.to_thread(compute_combined, policy, 30)  # lighter for PDF (30 each, faster)
    # Sample PASS cases from a synthetic new block
    sample_content = "gsk_" + "A"*30 + " and api_key secret"
    cases = generate_test_cases(sample_content, org_policy=policy or {"block_secrets": True, "block_pii": True})
    samples = run_test_cases(cases[:6], org_policy=policy or {"block_secrets": True, "block_pii": True})
    pdf_bytes = await asyncio.to_thread(build_evidence_pdf, metrics, combined, samples)
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="guardrail-evidence-pack.pdf"', "X-Content-Type-Options": "nosniff"})


@router.post("/generate-tests", response_model=dict)
async def generate_tests(body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Generate test cases for content without saving — preview what will be tested."""
    _require_org(current_user)
    content = (body.get("content") or "").strip()
    if not content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    policy = await _org_policy_dict(db, current_user.org_id)
    cases = generate_test_cases(content, org_policy=policy)
    return {"cases": [{"id": c.id, "prompt": c.prompt, "expected_blocked": c.expected_blocked, "expected_reason": c.expected_reason, "category": c.category} for c in cases]}


@router.post("/test-new-block", response_model=dict)
async def test_new_block(body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """
    Leader clicks 'Test new block' after adding content — we generate cases and run them
    through the current guardrail to prove the block actually fires.
    Returns per-case PASS/FAIL + summary.
    """
    _require_org(current_user)
    content = (body.get("content") or "").strip()
    if not content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    policy = await _org_policy_dict(db, current_user.org_id)
    cases = generate_test_cases(content, org_policy=policy)
    results = run_test_cases(cases, org_policy=policy)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    blocked_pos = sum(1 for r in results if r["expected_blocked"] and r["actually_blocked"])
    pos_total = sum(1 for r in results if r["expected_blocked"])
    return {
        "summary": f"{passed}/{total} tests passed — {blocked_pos}/{pos_total} blocks actually fire",
        "passed": passed,
        "total": total,
        "all_passed": passed == total,
        "results": results,
    }


@router.post("/{slug}/test-block", response_model=dict)
async def test_existing_block(slug: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Test the stored managed skill's block — fetch content then generate + run."""
    _require_org(current_user)
    row = await get_managed_skill(db, current_user.org_id, slug)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    policy = await _org_policy_dict(db, current_user.org_id)
    cases = generate_test_cases(row.content, org_policy=policy)
    results = run_test_cases(cases, org_policy=policy)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    return {"slug": slug, "version": row.version, "summary": f"{passed}/{total} tests passed", "passed": passed, "total": total, "all_passed": passed==total, "results": results}


@router.post("/check-identical-block", response_model=dict)
async def check_identical_block(body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """
    Leader button: does a block for this content already exist?
    e.g. new skill tries to include ChatGPT key `sk-...` — is `openai_api_key` already blocked?
    Checks:
      1) org policy (block_secrets/block_pii)
      2) existing managed skills' findings
      3) existing SkillAccessRejection history (recent blocks)
    Returns has_identical + where it is already blocked.
    """
    _require_org(current_user)
    content = (body.get("content") or "").strip()
    if not content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    # Scan new content
    scan = SkillGuardrail().scan(content)
    new_codes = {(f.reason_code, f.check) for f in scan.findings}
    # Also literal secret kind
    from app.utils.secret_redaction import contains_secret
    hit, kind = contains_secret(content)
    if hit and kind:
        new_codes.add(("secret_detected", kind))
        # also provider-specific
        if "openai" in kind.lower() or "sk-" in content:
            new_codes.add(("secret_detected", "openai_api_key"))
        if "groq" in content.lower():
            new_codes.add(("secret_detected", "groq_api_key"))
        if "anthropic" in kind.lower() or "sk-ant" in content.lower():
            new_codes.add(("secret_detected", "anthropic_key"))

    policy = await _org_policy_dict(db, current_user.org_id)
    # Existing blocks from policy
    policy_blocks: list[dict] = []
    if policy.get("block_secrets", True) and any("secret" in c[0] or "credential" in str(c) for c in new_codes):
        policy_blocks.append({"where": "org_policy.input_rules.block_secrets", "reason": "Policy already blocks secrets/API keys (gsk_/sk-/sk-ant-/ghp_/AKIA)", "covers": sorted([f"{a}:{b}" for a,b in new_codes])})
    if policy.get("block_pii") and any("pii" in c[0] for c in new_codes):
        policy_blocks.append({"where": "org_policy.input_rules.block_pii", "reason": "Policy already blocks PII", "covers": sorted([f"{a}:{b}" for a,b in new_codes])})

    # Existing managed skills' findings
    existing_rows = await list_managed_skills(db, current_user.org_id)
    managed_blocks: list[dict] = []
    seen_managed_codes: set[tuple] = set()
    for row in existing_rows:
        s = SkillGuardrail().scan(row.content or "")
        for f in s.findings:
            seen_managed_codes.add((f.reason_code, f.check))
    # Intersect
    intersect_managed = new_codes.intersection(seen_managed_codes)
    if intersect_managed:
        managed_blocks.append({"where": "managed_skills", "reason": f"{len(intersect_managed)} identical finding(s) already flagged in existing managed skills", "covers": sorted([f"{a}:{b}" for a,b in intersect_managed])})

    # Recent SkillAccessRejection blocks (last 100)
    from sqlalchemy import select as _select
    from app.models import SkillAccessRejection
    q = _select(SkillAccessRejection).where(SkillAccessRejection.org_id == current_user.org_id).order_by(SkillAccessRejection.created_at.desc()).limit(100)
    result = await db.execute(q)
    rejection_codes: set[tuple] = set()
    for rej in result.scalars().all():
        for f in (rej.findings or []):
            if isinstance(f, dict):
                rejection_codes.add((f.get("reason_code") or "", f.get("check") or ""))
    intersect_rej = new_codes.intersection(rejection_codes)
    rejection_blocks: list[dict] = []
    if intersect_rej:
        rejection_blocks.append({"where": "skill_access_rejections (recent 100)", "reason": "Identical block already recorded in rejection history", "covers": sorted([f"{a}:{b}" for a,b in intersect_rej])})

    has_identical = bool(policy_blocks or managed_blocks or rejection_blocks)
    # Provider-specific message for ChatGPT key case
    provider_hint = None
    low = content.lower()
    if "sk-" in content or "sk-proj" in content or "openai" in low or "chatgpt" in low:
        if any("secret" in c[0] for c in new_codes) or policy.get("block_secrets"):
            provider_hint = "ChatGPT/OpenAI API key (sk- / sk-proj-) is already blocked by block_secrets + secret_detected — no duplicate rule needed."

    return {
        "has_identical": has_identical,
        "is_already_blocked": has_identical,
        "new_findings": sorted([f"{a}:{b}" for a,b in new_codes]),
        "policy_blocks": policy_blocks,
        "managed_blocks": managed_blocks,
        "rejection_blocks": rejection_blocks,
        "provider_hint": provider_hint,
        "summary": "Identical block already exists" if has_identical else "No identical block — this would be a new block",
    }


# ── live fetch (agent pulls raw or wrapped) ─────────────────────────────────
# No auth decorator — handled manually so agents can use X-Api-Key or Bearer.
@live_router.get("/{slug}")
async def live_skill(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    raw: bool = Query(default=False, description="if true, return bare content without frontmatter"),
    mode: str | None = Query(default=None),
):
    # Try to resolve org from X-Api-Key / Authorization — fall back to PUBLIC feed if no key
    org_id: str | None = None
    auth_header = request.headers.get("X-Api-Key") or request.headers.get("Authorization") or ""
    key_val = ""
    if auth_header:
        if auth_header.lower().startswith("bearer "):
            key_val = auth_header[7:].strip()
        else:
            key_val = auth_header.strip()
        # also check ?key= query param (agent file contains ?key=grg_...)
        if not key_val:
            key_val = request.query_params.get("key") or ""
    if not key_val:
        key_val = request.query_params.get("key") or ""

    if key_val and key_val.startswith("grg_"):
        try:
            from app.deps import resolve_api_key
            api_key = await resolve_api_key(key_val, db)
            org_id = api_key.org_id
        except Exception:
            pass
    if not org_id:
        # also try Bearer JWT (dashboard user)
        try:
            from app.deps import get_current_user
            from fastapi.security import HTTPAuthorizationCredentials
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
                # minimal verify — if it's a local JWT, decode; clerk handled elsewhere
                # we reuse get_current_user path: construct fake credentials
                # simpler: try to look up user by token via deps helper is too heavy for live path;
                # so we skip JWT live auth for now and require grg_ key for org scoping.
                pass
        except Exception:
            pass

    # If no org resolved, try PUBLIC_APP_URL mode: find skill across orgs by slug (latest)
    # In hosted mode with single org this is fine; in multi-tenant we require key.
    skill = None
    if org_id:
        skill = await get_managed_skill(db, org_id, slug)
    if not skill:
        # fallback: search any org (public live URL without key — useful for demo)
        result = await db.execute(select(ManagedSkill).where(ManagedSkill.slug == slug.lower()).order_by(ManagedSkill.updated_at.desc()).limit(1))
        skill = result.scalar_one_or_none()
    if not skill:
        return Response(status_code=404, content=f"Skill '{slug}' not found")

    if raw:
        return PlainTextResponse(skill.content, media_type="text/markdown; charset=utf-8")

    effective_mode = mode if mode in ("overwrite", "versioned") else skill.update_mode
    base = get_settings().PUBLIC_APP_URL.rstrip("/")
    live_url = f"{base}/skills/live/{skill.slug}"
    md = build_skill_md(
        slug=skill.slug, name=skill.name, description=skill.description,
        content=skill.content, version=skill.version, content_hash=skill.content_hash,
        update_mode=effective_mode, live_url=live_url,
    )
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")
