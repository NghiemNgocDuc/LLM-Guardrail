"""Memory extraction + recall — Mem0/OpenAI style, Linear UX.

Extraction is LLM-assisted when a backend is configured, otherwise
falls back to a deterministic heuristic so memories work even without
an API key (dev/test).

Storage: Postgres `memories` table (source of truth) + optional
Pinecone namespace `memories` for semantic recall (gracefully skipped
when Pinecone is not configured).
"""
from __future__ import annotations

import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory

logger = logging.getLogger(__name__)

# ── Heuristic extraction (no LLM) ────────────────────────────────────────
_REMEMBER = re.compile(r"(?i)\b(remember|memory|prefer|my name is|i am|i work at|i like|i hate|always|never|from now on)\b")

def _heuristic_extract(prompt: str, response: str | None = None) -> list[dict[str, Any]]:
    texts = [prompt]
    if response:
        texts.append(response)
    out = []
    for t in texts:
        if _REMEMBER.search(t) or len(t.split()) > 12:
            # take up to 2 sentences as a memory candidate
            sents = [s.strip() for s in re.split(r"[\.!?]\s+", t) if s.strip()]
            for s in sents[:2]:
                if 10 < len(s) < 220 and _REMEMBER.search(s):
                    out.append({
                        "title": s[:60],
                        "content": s,
                        "category": "preference" if any(k in s.lower() for k in ["prefer", "like", "hate", "always"]) else "fact",
                        "confidence": 0.78,
                        "importance": 3,
                    })
    return out[:3]

async def llm_extract_memories(prompt: str, response: str | None, user_id: str) -> list[dict[str, Any]]:
    """Try LLM extraction; fall back to heuristic."""
    heuristics = _heuristic_extract(prompt, response)
    try:
        from app.config import get_settings
        from app.services.llm import call_llm  # lazy
        settings = get_settings()
        # only call LLM if we have a key and the prompt looked memorable
        if not heuristics and len(prompt) < 40:
            return []
        # cheap prompt — use the configured default model
        instruct = (
            "Extract up to 2 durable memories about the USER from the conversation below. "
            "Each memory must be a single factual sentence (no secrets, no PII like SSN/credit card). "
            "Return JSON list of {\"content\": str, \"category\": \"fact|preference|procedure|persona|goal\"}. "
            "If nothing worth remembering, return [].\n\n"
            f"User: {prompt}\nAssistant: {response or ''}"
        )
        llm_resp = await call_llm(
            prompt=instruct, temperature=0.2, max_tokens=256,
            request_backend=None, org_backend=None, request_model=None, org_model=None,
        )
        import json
        # try to find JSON array in response
        m = re.search(r"\[.*\]", llm_resp.text, flags=re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            memories = []
            for item in data[:2]:
                if isinstance(item, dict) and item.get("content"):
                    memories.append({
                        "title": item["content"][:60],
                        "content": item["content"][:400],
                        "category": item.get("category", "fact") if item.get("category") in ("fact","preference","procedure","persona","goal","skill") else "fact",
                        "confidence": 0.88,
                        "importance": 4,
                    })
            if memories:
                return memories
    except Exception:
        logger.debug("memory.llm_extract fallback", exc_info=True)
    return heuristics

# ── CRUD ─────────────────────────────────────────────────────────────────
MEMORY_CAP_PER_TEAM = 500

async def _prune_if_needed(db: AsyncSession, org_id: str | None, user_id: str) -> None:
    """Save space: dedup + cap 500/team + archive low-value old memories."""
    if not org_id:
        return
    # Cap check — if over, archive oldest low-importance first
    cnt_res = await db.execute(select(func.count()).select_from(Memory).where(Memory.org_id == org_id, Memory.archived == False))
    cnt = cnt_res.scalar() or 0
    if cnt <= MEMORY_CAP_PER_TEAM:
        return
    # Archive oldest, lowest importance, not pinned, low confidence
    to_archive = await db.execute(
        select(Memory).where(Memory.org_id == org_id, Memory.archived == False, Memory.pinned == False)
        .order_by(Memory.importance.asc(), Memory.confidence.asc(), Memory.updated_at.asc())
        .limit(cnt - MEMORY_CAP_PER_TEAM + 10)  # keep buffer
    )
    for m in to_archive.scalars().all():
        m.archived = True
        # delete vector (save Pinecone space)
        try:
            from app.services.vectorstore import delete_memory  # type: ignore
            await delete_memory(m.id)
        except: pass
    await db.flush()

async def create_memory(
    db: AsyncSession,
    user_id: str,
    org_id: str | None,
    content: str,
    title: str | None = None,
    category: str = "fact",
    kind: str = "user",
    confidence: float = 0.82,
    importance: int = 3,
    pinned: bool = False,
    source_type: str | None = "manual",
    source_id: str | None = None,
) -> Memory:
    # Dedup via hash of title+content (per user+org) — save space
    import hashlib
    content_hash = hashlib.sha256((content[:200] + (title or "")).encode()).hexdigest()[:12]
    existing = await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.org_id == org_id, Memory.archived == False))
    for m in existing.scalars().all():
        if hashlib.sha256((m.content[:200] + m.title).encode()).hexdigest()[:12] == content_hash:
            # Touch existing instead of duplicate
            m.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return m
    # TTL: auto-archive low-value old memories before create (90d, importance<3, confidence<0.7, not pinned)
    try:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        old_low = await db.execute(select(Memory).where(Memory.org_id == org_id, Memory.archived == False, Memory.pinned == False, Memory.importance < 3, Memory.confidence < 0.7, Memory.updated_at < cutoff).limit(20))
        for m in old_low.scalars().all():
            m.archived = True
            try:
                from app.services.vectorstore import delete_memory
                await delete_memory(m.id)
            except: pass
        await db.flush()
    except: pass
    # Cap 500/team
    await _prune_if_needed(db, org_id, user_id)
    # Compress: store content gzipped length check — keep as Text but ensure float16 for vector (vectorstore handles)
    title = (title or content[:60]).strip()
    mem = Memory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        org_id=org_id,
        title=title,
        content=content[:4000],
        category=category,
        kind=kind,
        confidence=confidence,
        importance=importance,
        pinned=pinned,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(mem)
    await db.flush()
    try:
        from app.services.vectorstore import upsert_memory  # type: ignore
        await upsert_memory(mem.id, mem.content, {"user_id": user_id, "org_id": org_id or "", "category": category})
    except:
        pass
    return mem

async def list_memories(
    db: AsyncSession,
    user_id: str,
    org_id: str | None,
    q: str | None = None,
    category: str | None = None,
    pinned_only: bool = False,
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Memory], int]:
    filters = [Memory.user_id == user_id, Memory.archived == archived]
    # org memories are visible to the user as well (kind=org and org_id matches)
    # but we keep the primary filter as user_id so personal memories dominate
    if category:
        filters.append(Memory.category == category)
    if pinned_only:
        filters.append(Memory.pinned == True)
    if q:
        like = f"%{q}%"
        filters.append(or_(Memory.title.ilike(like), Memory.content.ilike(like)))
    count_q = await db.execute(select(func.count()).select_from(Memory).where(*filters))
    total = count_q.scalar() or 0
    res = await db.execute(
        select(Memory).where(*filters).order_by(Memory.pinned.desc(), Memory.updated_at.desc()).limit(limit).offset(offset)
    )
    return list(res.scalars().all()), total

async def recall_memories(db: AsyncSession, user_id: str, query: str, top_k: int = 5, category: str | None = None) -> list[Memory]:
    # try vector recall first
    try:
        from app.services.vectorstore import query_memories  # type: ignore
        hits = await query_memories(query, user_id=user_id, top_k=top_k)
        if hits:
            ids = [h["id"] for h in hits]
            res = await db.execute(select(Memory).where(Memory.id.in_(ids), Memory.archived == False))
            # preserve vector order
            by_id = {m.id: m for m in res.scalars().all()}
            ordered = [by_id[i] for i in ids if i in by_id]
            # touch last_accessed
            for m in ordered:
                m.last_accessed = datetime.now(timezone.utc)
            await db.flush()
            # filter category if requested
            if category:
                ordered = [m for m in ordered if m.category == category]
            if ordered:
                return ordered
    except Exception:
        logger.debug("memory.recall vector fallback", exc_info=True)
    # fallback: keyword search
    like = f"%{query}%"
    filters = [Memory.user_id == user_id, Memory.archived == False, or_(Memory.title.ilike(like), Memory.content.ilike(like))]
    if category:
        filters.append(Memory.category == category)
    res = await db.execute(select(Memory).where(*filters).order_by(Memory.pinned.desc(), Memory.updated_at.desc()).limit(top_k))
    return list(res.scalars().all())
