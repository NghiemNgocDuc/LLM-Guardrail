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

import hashlib
import json
from types import SimpleNamespace
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import CurrentUser, get_current_user, resolve_api_key
from app.models import ManagedSkill, OrgMembership, OrgPolicy, User
from app.services.skill_store import (
    create_managed_skill,
    delete_managed_skill,
    get_managed_skill,
    list_managed_skills,
    list_skill_versions,
    update_managed_skill,
    skill_revision,
)
from guardrails.skill_conflict import build_skill_md, check_skill_conflicts
from app.services.skill_metrics import compute_metrics as compute_skill_metrics
from app.services.combined_benchmark import compute_combined
from app.services.skill_rejections import record_rejection
from app.services.skill_user_overrides import apply_saved_scan_overrides, content_digest
from guardrails.skill import SkillGuardrail
from guardrails.test_case_generator import generate_test_cases, run_test_cases

router = APIRouter(prefix="/skills/managed", tags=["Managed Skills"])
live_router = APIRouter(prefix="/skills/live", tags=["Managed Skills Live"])

class CreateSkillRequest(BaseModel):
    model_config = {"extra": "forbid"}
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    content: str = Field(min_length=1, max_length=256_000)
    update_mode: Literal["overwrite", "versioned"] = "overwrite"
    block_on_conflict: bool = Field(default=False, strict=True)

    @field_validator("slug", "name", "content")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

class UpdateSkillRequest(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, min_length=1, max_length=256_000)
    update_mode: Literal["overwrite", "versioned"] | None = None
    block_on_conflict: bool = Field(default=False, strict=True)
    expected_version: int | None = Field(default=None, ge=1)
    expected_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("name", "content")
    @classmethod
    def nonblank(cls, value):
        return CreateSkillRequest.nonblank(value)

class SkillContentRequest(BaseModel):
    model_config = {"extra": "forbid"}
    content: str = Field(min_length=1, max_length=256_000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value):
        return CreateSkillRequest.nonblank(value)

class ConflictRequest(SkillContentRequest):
    exclude_slug: str = Field(default="", max_length=80)

class BlockTestRequest(SkillContentRequest):
    max_total: int = Field(default=500, ge=1, le=500)

def _skill_document(row, mode: str, live_url: str, *, raw: bool = False) -> PlainTextResponse:
    if hashlib.sha256(row.content.encode("utf-8")).hexdigest() != row.content_hash:
        raise HTTPException(status_code=500, detail="Stored skill integrity check failed")
    try:
        document = row.content if raw else build_skill_md(slug=row.slug, name=row.name, description=row.description, content=row.content, version=row.version, content_hash=row.content_hash, update_mode=mode, live_url=live_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"{row.slug}.md" if mode == "overwrite" else f"{row.slug}.v{row.version}.md"
    return PlainTextResponse(document, media_type="text/markdown; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store",
        "Vary": "Authorization, X-Api-Key",
        "X-Content-Type-Options": "nosniff",
        "X-Skill-Slug": row.slug,
        "X-Skill-Version": str(row.version),
        "X-Skill-Content-SHA256": row.content_hash,
        "X-Skill-Document-SHA256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
        "X-Skill-Update-Mode": mode,
        "X-Skill-Revision": skill_revision(row),
    })

async def _live_actor(request: Request, db: AsyncSession):
    """Authenticate once; never widen a failed/missing lookup to a public tenant."""
    supplied_key = request.headers.get("X-Api-Key")
    authorization = request.headers.get("Authorization", "")
    bearer = None
    if authorization:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(status_code=401, detail="Use Bearer authentication or X-Api-Key")
        bearer = parts[1]
    raw_key = supplied_key if supplied_key is not None else bearer if bearer and bearer.startswith("grg_") else None if bearer else request.query_params.get("key")
    if raw_key is not None:
        key = await resolve_api_key(raw_key.strip(), db)
        if "skills:read" not in (key.scopes or []):
            raise HTTPException(status_code=403, detail="This key needs the skills:read scope to download skills")
        owner = await db.get(User, key.owner_id)
        if owner is None or not owner.is_active:
            raise HTTPException(status_code=401, detail="The key owner is inactive")
        if not key.org_id:
            raise HTTPException(status_code=404, detail="No organization")
        if owner.org_id != key.org_id:
            membership = await db.execute(select(OrgMembership).where(OrgMembership.user_id == owner.id, OrgMembership.org_id == key.org_id))
            if membership.scalar_one_or_none() is None:
                raise HTTPException(status_code=403, detail="The key owner no longer belongs to this workspace")
        return SimpleNamespace(id=owner.id, org_id=key.org_id, is_active=True)
    if bearer:
        user = await get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer), db)
        _require_org(user)
        return user
    raise HTTPException(status_code=401, detail="Authenticate with a scoped gateway key or a signed-in session")

async def _authorize_distribution(db: AsyncSession, actor, row, response: PlainTextResponse, *, raw: bool = False) -> None:
    """Stored drafts never become agent context without a current scan decision."""
    filename = f"{row.slug}.md"
    # Scan authored agent context, including behavioral descriptions. Generated
    # timestamps/footer do not change the stable approval identity on each fetch.
    metadata = "" if raw else "\n".join(line for line in response.body.decode("utf-8").split("\n---\n", 1)[0].splitlines() if line.startswith(("name:", "description:", "live_url:")))
    authored_context = metadata + "\n\n" + row.content
    identity = json.dumps({"revision": skill_revision(row), "mode": response.headers["X-Skill-Update-Mode"], "raw": raw, "authored_context": authored_context}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result = SkillGuardrail().scan(authored_context)
    decision = await apply_saved_scan_overrides(db, actor, result, identity, filename)
    if decision.blocked:
        summary = f"Managed skill v{row.version} · {response.headers['X-Skill-Update-Mode']} · {'raw' if raw else 'wrapped'} · revision {skill_revision(row)[:12]}. {decision.rejection_summary or 'Review required.'}"
        rejection = await record_rejection(db, user=actor, filename=filename, source="managed_download", findings=decision.blocking, summary=summary, content_preview=authored_context, content_sha256=content_digest(identity))
        await db.commit()
        raise HTTPException(status_code=422, detail={"message": "This skill is blocked from agent distribution. Review its exact findings in the review queue, then retry the download.", "rejection_id": rejection.id, "blocked": True})
    # Commit single-use grant consumption before returning a permitted document.
    await db.commit()


async def _require_private_safe_draft(db: AsyncSession, actor, *, slug: str, name: str, description: str, content: str) -> None:
    """Private storage accepts no flagged source, even after an approval.

    Scan raw authored fields rather than an escaped Markdown wrapper. The
    private rejection service retains only static labels and opaque identity;
    rejected text never enters the managed skill or its version history.
    """
    if not getattr(get_settings(), "PRIVATE_MODE", False):
        return
    authored_context = "\n".join((name, description, "", content))
    result = SkillGuardrail().scan(authored_context)
    if result.safe:
        return
    identity = json.dumps({"name": name, "description": description, "content": content}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    rejection = await record_rejection(
        db, user=actor, filename=f"{slug}.md", source="managed_write",
        findings=result.findings, summary="Managed skill draft rejected in private mode.",
        content_sha256=content_digest(identity),
    )
    await db.commit()
    raise HTTPException(status_code=422, detail={
        "message": "Private mode cannot store flagged skill content. Redact or remove the flagged instructions before saving. Approval does not permit unsafe drafts to be stored.",
        "rejection_id": rejection.id, "blocked": True, "private_mode": True,
    })


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
            "revision": skill_revision(r),
        }
        for r in rows
    ]


@router.post("", response_model=dict, status_code=201)
async def create_skill(
    body: CreateSkillRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    _require_org(current_user)
    slug = (body.slug or body.name or "").strip()
    name = (body.name or slug).strip()
    description = body.description
    content = body.content
    update_mode = body.update_mode

    await _require_private_safe_draft(db, current_user, slug=slug, name=name, description=description, content=content)

    # conflict check before write (advisory — still allow creation but return conflicts)
    existing = await _existing_as_dicts(db, current_user.org_id)
    policy = await _org_policy_dict(db, current_user.org_id)
    conflicts = check_skill_conflicts(content, existing_skills=existing, org_policy=policy, org_id=current_user.org_id)

    # optional hard block: if body says block_on_conflict and critical, reject
    if body.block_on_conflict and conflicts.blocked_by_policy:
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
        "revision": skill_revision(row),
        "conflicts": [c.__dict__ for c in conflicts.conflicts],
        "has_conflict": conflicts.has_conflict,
        "blocked_by_policy": conflicts.blocked_by_policy,
        "conflict_summary": conflicts.summary,
    }


@router.get("/metrics", response_model=dict)
async def skill_metrics(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Live fixture scores. Register this static path before the slug route."""
    _require_org(current_user)
    policy = await _org_policy_dict(db, current_user.org_id)
    return compute_skill_metrics(org_policy=policy or {"block_secrets": True, "block_pii": True})


@router.get("/{slug}", response_model=dict)
async def get_skill(slug: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    row = await get_managed_skill(db, current_user.org_id, slug)
    if not row:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    return {
        "slug": row.slug, "name": row.name, "description": row.description,
        "content": row.content, "version": row.version,
        "hash": row.content_hash[:12], "full_hash": row.content_hash,
        "update_mode": row.update_mode,
        "revision": skill_revision(row),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.put("/{slug}", response_model=dict)
async def update_skill(slug: str, body: UpdateSkillRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_admin(current_user)
    _require_org(current_user)
    new_content = body.content
    if getattr(get_settings(), "PRIVATE_MODE", False):
        # Hold the same row lock used by the store through scan and write, so
        # the effective unchanged fields cannot change between those steps.
        stored = (await db.execute(select(ManagedSkill).where(
            ManagedSkill.org_id == current_user.org_id,
            ManagedSkill.slug == slug.strip().lower(),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if stored is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        if (body.expected_version is not None and body.expected_version != stored.version) or (body.expected_revision is not None and body.expected_revision != skill_revision(stored)):
            raise HTTPException(status_code=409, detail="This skill changed since you opened it. Reload the latest version before saving your draft.")
        await _require_private_safe_draft(
            db, current_user, slug=stored.slug,
            name=body.name.strip() if body.name is not None else stored.name,
            description=body.description if body.description is not None else stored.description,
            content=new_content if new_content is not None else stored.content,
        )
    # conflict check if content is being changed
    conflicts = None
    if new_content is not None:
        # existing skills except the one being updated (so we don't self-conflict)
        existing = [d for d in await _existing_as_dicts(db, current_user.org_id) if d["slug"] != slug.lower()]
        policy = await _org_policy_dict(db, current_user.org_id)
        conflicts = check_skill_conflicts(new_content, existing_skills=existing, org_policy=policy, org_id=current_user.org_id)
        if body.block_on_conflict and conflicts.blocked_by_policy:
            raise HTTPException(status_code=422, detail={
                "message": "Update conflicts with current API-key leak protection",
                "conflicts": [c.__dict__ for c in conflicts.conflicts],
                "summary": conflicts.summary,
            })

    row = await update_managed_skill(
        db, org_id=current_user.org_id, slug=slug,
        name=body.name, description=body.description,
        content=new_content, update_mode=body.update_mode,
        updated_by=current_user.id,
        expected_version=body.expected_version, expected_revision=body.expected_revision,
    )
    await db.commit()
    out: dict = {
        "slug": row.slug, "name": row.name, "description": row.description,
        "version": row.version, "hash": row.content_hash[:12], "full_hash": row.content_hash,
        "update_mode": row.update_mode,
        "revision": skill_revision(row),
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
async def check_conflict(body: ConflictRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    content = body.content
    if not content.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    # exclude slug if checking an update to existing skill (avoid self-conflict)
    exclude = body.exclude_slug.strip().lower()
    existing = await _existing_as_dicts(db, current_user.org_id)
    if exclude:
        existing = [d for d in existing if d["slug"] != exclude]
    policy = await _org_policy_dict(db, current_user.org_id)
    res = check_skill_conflicts(content, existing_skills=existing, org_policy=policy, org_id=current_user.org_id)
    return {
        "has_conflict": res.has_conflict,
        "safe": res.safe,
        "blocked_by_policy": res.blocked_by_policy,
        "summary": res.summary,
        "conflicts": [c.__dict__ for c in res.conflicts],
        "policy_findings": res.policy_findings,
    }


@router.post("/{slug}/check-conflict", response_model=dict)
async def check_conflict_for_slug(slug: str, body: SkillContentRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    _require_org(current_user)
    content = body.content
    if not content.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    existing = [d for d in await _existing_as_dicts(db, current_user.org_id) if d["slug"] != slug.lower()]
    policy = await _org_policy_dict(db, current_user.org_id)
    res = check_skill_conflicts(content, existing_skills=existing, org_policy=policy, org_id=current_user.org_id)
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
    mode: Literal["overwrite", "versioned"] | None = Query(default=None),
    live_url: HttpUrl | None = Query(default=None),
):
    _require_org(current_user)
    if live_url:
        parsed = urlsplit(str(live_url))
        credential_fields = {"key", "token", "api_key", "api-key", "access_token", "authorization", "secret", "password"}
        if parsed.username or parsed.password or any(name.lower() in credential_fields for name, _ in parse_qsl(parsed.query)):
            raise HTTPException(status_code=400, detail="Do not embed authentication credentials in a skill's live URL. Use an authorization header.")
    row = await get_managed_skill(db, current_user.org_id, slug)
    if not row:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
    # caller can override download mode; otherwise use the skill's stored update_mode
    effective_mode = mode or row.update_mode
    # If caller forced a different mode than stored, we still honor it for THIS download only
    base = get_settings().PUBLIC_APP_URL.rstrip("/")
    default_live = f"{base}/skills/live/{row.slug}"
    response = _skill_document(row, effective_mode, str(live_url) if live_url else default_live)
    await _authorize_distribution(db, current_user, row, response)
    return response


# ── metrics + identical-block scan + auto test generation ──────────────────

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
async def generate_tests(body: SkillContentRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Generate test cases for content without saving — preview what will be tested."""
    _require_org(current_user)
    content = body.content
    if not content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    policy = await _org_policy_dict(db, current_user.org_id)
    cases = generate_test_cases(content, org_policy=policy)
    return {"cases": [{"id": c.id, "prompt": c.prompt, "expected_blocked": c.expected_blocked, "expected_reason": c.expected_reason, "category": c.category} for c in cases]}


@router.post("/test-new-block", response_model=dict)
async def test_new_block(body: BlockTestRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """
    Leader clicks 'Test new block' after adding content — we generate cases and run them
    through the current guardrail to prove the block actually fires.
    Returns per-case PASS/FAIL + summary.
    """
    _require_org(current_user)
    # Keep direct Python callers on the same validation path as HTTP callers.
    if isinstance(body, dict):
        body = BlockTestRequest.model_validate(body)
    content = body.content
    if not content:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="content is required")
    policy = await _org_policy_dict(db, current_user.org_id)
    cases = generate_test_cases(content, org_policy=policy)[:body.max_total]
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
async def check_identical_block(body: SkillContentRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    """Compare finding categories without treating history as enforcement.

    This read-only check reports the default skill scanner's decision and
    configured input-policy coverage. It neither evaluates the complete chat
    runtime nor consumes an exact-content approval.
    """
    _require_org(current_user)
    if isinstance(body, dict):
        body = SkillContentRequest.model_validate(body)
    content = body.content
    scan = SkillGuardrail().scan(content)
    new_codes = {(f.reason_code, f.check) for f in scan.findings}
    policy = await _org_policy_dict(db, current_user.org_id)
    # These are configured rule categories, not a complete runtime verdict.
    credential_codes = {"gateway_api_key", "credential_assignment", "env_assignment", "env_exfiltration_probe"}
    secret_codes = {(f.reason_code, f.check) for f in scan.findings if f.category == "secret" or f.reason_code in credential_codes}
    pii_codes = {(f.reason_code, f.check) for f in scan.findings if f.category == "pii"}
    policy_blocks: list[dict] = []
    if policy.get("block_secrets", True) and secret_codes:
        policy_blocks.append({"where": "org_policy.input_rules.block_secrets", "reason": "Secret blocking is configured for these finding categories. The complete runtime decision can also depend on custom rules and approvals.", "covers": sorted(f"{a}:{b}" for a, b in secret_codes)})
    pii_mode = policy.get("pii_mode") or policy.get("pii_redaction_mode") or "block"
    if policy.get("block_pii") and pii_mode == "block" and pii_codes:
        policy_blocks.append({"where": "org_policy.input_rules.block_pii", "reason": "PII blocking is configured. Coverage depends on the configured PII patterns and complete runtime policy.", "covers": sorted(f"{a}:{b}" for a, b in pii_codes)})

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
        managed_blocks.append({"where": "managed_skills", "reason": f"{len(intersect_managed)} matching finding category/categories in existing managed drafts. A stored finding is not an enforced block or an approval.", "covers": sorted([f"{a}:{b}" for a,b in intersect_managed])})

    # Recent SkillAccessRejection blocks (last 100)
    from sqlalchemy import select as _select
    from app.models import SkillAccessRejection
    q = _select(SkillAccessRejection).where(SkillAccessRejection.org_id == current_user.org_id, SkillAccessRejection.user_id == current_user.id).order_by(SkillAccessRejection.created_at.desc()).limit(100)
    result = await db.execute(q)
    rejection_codes: set[tuple] = set()
    for rej in result.scalars().all():
        for f in (rej.findings or []):
            if isinstance(f, dict):
                rejection_codes.add((f.get("reason_code") or "", f.get("check") or ""))
    intersect_rej = new_codes.intersection(rejection_codes)
    rejection_blocks: list[dict] = []
    if intersect_rej:
        rejection_blocks.append({"where": "skill_access_rejections (your recent 100)", "reason": "Matching finding categories appear in your rejection history. Previous cases do not determine this content's current decision.", "covers": sorted([f"{a}:{b}" for a,b in intersect_rej])})

    has_identical = bool(policy_blocks or managed_blocks or rejection_blocks)
    # Provider names alone never establish that a credential was detected.
    import re
    provider_hint = None
    openai_literal = re.search(r"\b" + "sk" + r"-(?!ant-)[A-Za-z0-9_-]{20,}\b", content)
    if openai_literal and policy.get("block_secrets", True) and secret_codes:
        provider_hint = "An OpenAI-style API key was detected and secret blocking is configured. Verify the complete runtime policy before relying on that coverage."

    scanner_blocked = not scan.safe
    summary = "Current skill scan would block this content." if scanner_blocked else "Current skill scan found no blocking findings."
    summary += " Matching finding categories were found." if has_identical else " No matching configured or historical finding categories were found."
    summary += " Coverage is advisory; history does not enforce a block."

    return {
        "has_identical": has_identical,
        "is_already_blocked": scanner_blocked,
        "scanner_blocked": scanner_blocked,
        "coverage_advisory": True,
        "runtime_decision_checked": False,
        "new_findings": sorted([f"{a}:{b}" for a,b in new_codes]),
        "policy_blocks": policy_blocks,
        "managed_blocks": managed_blocks,
        "rejection_blocks": rejection_blocks,
        "provider_hint": provider_hint,
        "summary": summary,
    }


# ── live fetch (agent pulls raw or wrapped) ─────────────────────────────────
@live_router.get("/{slug}")
async def live_skill(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    raw: bool = Query(default=False),
    mode: Literal["overwrite", "versioned"] | None = Query(default=None),
):
    actor = await _live_actor(request, db)
    skill = await get_managed_skill(db, actor.org_id, slug)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found in this workspace")
    base = get_settings().PUBLIC_APP_URL.rstrip("/")
    response = _skill_document(skill, mode or skill.update_mode, f"{base}/skills/live/{skill.slug}", raw=raw)
    await _authorize_distribution(db, actor, skill, response, raw=raw)
    return response
