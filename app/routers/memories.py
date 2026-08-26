"""Memories — user long-term memory, Mem0 + OpenAI style.

- List / create / update / archive
- Semantic recall (Pinecone + keyword fallback)
- Extract from last conversation (LLM-assisted)

All routes are user-scoped (CurrentUser). Org memories (kind=org) are
visible to org members but only admins can create org kind.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import CurrentUser
from app.i18n import _t
from app.models import Memory
from app.schemas import MemoryCreate, MemoryOut, MemoryRecallRequest, MemoryRecallOut, MemoryUpdate
from app.services.memory import create_memory, list_memories, recall_memories, llm_extract_memories

router = APIRouter(prefix="/memories", tags=["Memories"])

@router.get("", response_model=list[MemoryOut])
async def list_mem(current_user: CurrentUser, q: str | None = None, category: str | None = None, pinned_only: bool = False, archived: bool = False, limit: int = Query(50, ge=1, le=100), offset: int = 0, db: AsyncSession = Depends(get_db)):
    items, _ = await list_memories(db, current_user.id, current_user.org_id, q=q, category=category, pinned_only=pinned_only, archived=archived, limit=limit, offset=offset)
    return items

@router.get("/stats")
async def stats(current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    # counts per category, pinned, total
    from app.services.memory import list_memories as lm
    items, total = await lm(db, current_user.id, current_user.org_id, limit=1000)
    by_cat: dict[str, int] = {}
    pinned = 0
    for m in items:
        by_cat[m.category] = by_cat.get(m.category, 0) + 1
        if m.pinned:
            pinned += 1
    return {"total": total, "pinned": pinned, "by_category": by_cat}

@router.post("", response_model=MemoryOut, status_code=201)
async def create_mem(body: MemoryCreate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    if body.kind == "org" and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create org memories")
    mem = await create_memory(db, current_user.id, current_user.org_id, content=body.content, title=body.title, category=body.category, kind=body.kind, confidence=body.confidence or 0.85, importance=body.importance or 3, pinned=body.pinned, source_type="manual")
    await db.commit()
    return mem

@router.get("/{memory_id}", response_model=MemoryOut)
async def get_mem(memory_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    mem = await db.get(Memory, memory_id)
    if not mem or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    # touch last_accessed
    from datetime import datetime, timezone
    mem.last_accessed = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    return mem

@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_mem(memory_id: str, body: MemoryUpdate, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    mem = await db.get(Memory, memory_id)
    if not mem or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(mem, k, v)
    await db.flush()
    await db.commit()
    return mem

@router.delete("/{memory_id}", status_code=204)
async def delete_mem(memory_id: str, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    mem = await db.get(Memory, memory_id)
    if not mem or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    # soft-delete -> archive
    mem.archived = True
    await db.flush()
    await db.commit()
    return None

@router.post("/recall", response_model=MemoryRecallOut)
async def recall(body: MemoryRecallRequest, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    mems = await recall_memories(db, current_user.id, body.query, top_k=body.top_k, category=body.category)
    return MemoryRecallOut(memories=mems, query=body.query)

@router.post("/extract/preview")
async def extract_preview(body: dict, current_user: CurrentUser):
    prompt = (body.get("prompt") or "")[:4000]
    response_text = body.get("response")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")
    candidates = await llm_extract_memories(prompt, response_text, current_user.id)
    return {"candidates": candidates}

@router.post("/extract/confirm", response_model=list[MemoryOut])
async def extract_confirm(body: dict, current_user: CurrentUser, db: AsyncSession = Depends(get_db)):
    items = body.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="items required")
    created: list[Memory] = []
    for it in items[:5]:
        content = (it.get("content") or "").strip()
        if not content:
            continue
        mem = await create_memory(
            db, current_user.id, current_user.org_id,
            content=content,
            title=it.get("title") or content[:60],
            category=it.get("category") or "fact",
            confidence=float(it.get("confidence") or 0.82),
            importance=int(it.get("importance") or 3),
            source_type="chat",
            source_id=it.get("source_id"),
        )
        created.append(mem)
    await db.commit()
    return created
