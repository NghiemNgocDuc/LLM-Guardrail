"""Pinecone vector store admin — seed blocked patterns, query similarity."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.i18n import _t
from app.models import OrgPolicy

router = APIRouter(prefix="/vector", tags=["Vector"])


class SeedPatternsRequest(BaseModel):
    model_config = {"extra": "forbid"}
    texts: list[str] = Field(min_length=1, description="Blocked text patterns to index for semantic matching")


class SeedPatternsResponse(BaseModel):
    indexed: int
    message: str


@router.post("/seed", response_model=SeedPatternsResponse)
async def seed_blocked_patterns(body: SeedPatternsRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if not current_user.is_admin or not current_user.org_id:
        raise HTTPException(status_code=403, detail=_t("vector.admin_required"))
    result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == current_user.org_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail=_t("vector.policy_not_found"))
    rules = dict(policy.input_rules or {})
    existing = rules.get("semantic_blocked_texts", [])
    merged = list(set(existing + body.texts))
    rules["semantic_blocked_texts"] = merged
    policy.input_rules = rules
    await db.flush()
    return SeedPatternsResponse(indexed=len(body.texts), message=f"Seeded {len(body.texts)} patterns (total {len(merged)})")


class SimilarityQuery(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1)
    top_k: int = 3


@router.post("/query")
async def query_similar(body: SimilarityQuery, current_user: CurrentUser):
    from app.services.vectorstore import semantic_similarity
    results = await semantic_similarity(body.text, body.top_k)
    return {"results": results}
