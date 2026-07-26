"""Pinecone vector store — semantic guardrail checks, conversation indexing."""
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_pinecone_initialized = False
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def init() -> None:
    global _pinecone_initialized
    if _pinecone_initialized:
        return
    settings = get_settings()
    if not settings.PINECONE_API_KEY:
        logger.info("vectorstore.not_configured — skipping Pinecone init")
        return
    try:
        from pinecone import Pinecone, ServerlessSpec
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        if settings.PINECONE_INDEX_NAME not in pc.list_indexes().names():
            pc.create_index(
                name=settings.PINECONE_INDEX_NAME,
                dimension=384,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=settings.PINECONE_ENVIRONMENT or "us-east-1"),
            )
        _pinecone_initialized = True
        logger.info("vectorstore.connected index=%s", settings.PINECONE_INDEX_NAME)
    except Exception:
        logger.exception("vectorstore.init_failed")


def _index():
    if not _pinecone_initialized:
        return None
    from pinecone import Pinecone
    settings = get_settings()
    try:
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        return pc.Index(settings.PINECONE_INDEX_NAME)
    except Exception:
        logger.exception("vectorstore.index_failed")
        return None


async def upsert_conversation(
    session_id: str,
    prompt: str,
    response: str | None,
    status: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    idx = _index()
    if idx is None:
        return
    if not get_settings().PINECONE_STORE_CONVERSATIONS:
        return
    try:
        import uuid

        model = _get_embedding_model()
        text = f"prompt: {prompt}\nresponse: {response or ''}"
        vec = model.encode(text).tolist()
        idx.upsert(
            vectors=[(
                str(uuid.uuid4()),
                vec,
                {
                    "session_id": session_id,
                    "prompt": prompt[:500],
                    "response": (response or "")[:500],
                    "status": status,
                    **(metadata or {}),
                },
            )]
        )
    except Exception:
        logger.exception("vectorstore.upsert_failed")


async def semantic_similarity(text: str, top_k: int = 3) -> list[dict]:
    idx = _index()
    if idx is None:
        return []
    try:
        model = _get_embedding_model()
        vec = model.encode(text).tolist()
        results = idx.query(vector=vec, top_k=top_k, include_metadata=True)
        return [
            {
                "score": m.score,
                "session_id": m.metadata.get("session_id", ""),
            }
            for m in results.matches
        ]
    except Exception:
        logger.exception("vectorstore.query_failed")
        return []


def find_similar_blocked(blocked_texts: list[str], prompt: str, threshold: float = 0.85) -> tuple[bool, float, str]:
    if not blocked_texts:
        return False, 0.0, ""
    try:
        model = _get_embedding_model()

        prompt_vec = model.encode(prompt)
        blocked_vecs = model.encode(blocked_texts)

        import numpy as np
        prompt_norm = prompt_vec / np.linalg.norm(prompt_vec)
        blocked_norms = blocked_vecs / np.linalg.norm(blocked_vecs, axis=1, keepdims=True)

        scores = blocked_norms @ prompt_norm
        max_idx = int(np.argmax(scores))
        max_score = float(scores[max_idx])

        if max_score >= threshold:
            return True, max_score, blocked_texts[max_idx][:200]
        return False, max_score, ""
    except Exception:
        logger.exception("vectorstore.similarity_check_failed")
        return False, 0.0, ""


def shutdown() -> None:
    global _pinecone_initialized
    _pinecone_initialized = False
