"""
OpenAI-compatible shim — Otari-style `POST /v1/chat/completions`.

Lets any OpenAI SDK hit the guardrail gateway without code changes:
  client = OpenAI(base_url=".../v1", api_key="grg_...")
  client.chat.completions.create(model="...", messages=[...])

Flow reuses the same gates as /chat: org policy -> input guardrail (regex
+ ML 2nd stage) -> provider routing (40+ via litellm/openai_compatible) ->
output guardrail -> audit log. Streaming (SSE) supported.
"""
import hashlib
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import AuthedAPIKey
from app.models import OrgPolicy
from app.routers.chat import _log_request
from app.services.llm import call_llm, stream_llm
from guardrails.input import InputGuardrail
from guardrails.output import OutputGuardrail

settings = get_settings()
router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

_DEFAULT_INPUT = {"block_secrets": True, "block_pii": True, "block_prompt_injection": True, "block_jailbreak": True}
_DEFAULT_OUTPUT = {"block_toxic_content": True}
_DEFAULT_TOPIC = {"blocked_topics": []}
_DEFAULT_COMPLIANCE = {}


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for m in messages or []:
        role = str(m.get("role", "user"))
        content = m.get("content", "")
        if isinstance(content, list):  # OpenAI content blocks
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(texts)
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


@router.get("/models")
async def list_models(api_key: AuthedAPIKey):
    """Otari-style model catalog — static list of routed backends."""
    from app.services.llm import _DEFAULT_MODELS
    return {
        "object": "list",
        "data": [
            {"id": model, "object": "model", "owned_by": backend}
            for backend, model in sorted(_DEFAULT_MODELS.items())
        ],
    }


@router.post("/chat/completions")
async def chat_completions(body: dict[str, Any], request: Request, api_key: AuthedAPIKey, db: AsyncSession = Depends(get_db)):
    start = time.monotonic()
    if "chat" not in (list(api_key.scopes) if api_key.scopes else ["chat"]):
        raise HTTPException(status_code=403, detail="API key missing 'chat' scope")

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    prompt = _messages_to_prompt(messages)
    model_req = body.get("model")
    temperature = float(body.get("temperature", 0.7))
    max_tokens = int(body.get("max_tokens", 1024))
    stream = bool(body.get("stream", False))

    # Org policy (same as /chat)
    policy: OrgPolicy | None = None
    if api_key.org_id:
        res = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == api_key.org_id))
        policy = res.scalar_one_or_none()
    in_rules = policy.input_rules if policy else _DEFAULT_INPUT
    out_rules = policy.output_rules if policy else _DEFAULT_OUTPUT
    topic = policy.topic_policy if policy else _DEFAULT_TOPIC
    comp = policy.compliance_rules if policy else _DEFAULT_COMPLIANCE

    in_guard = InputGuardrail(in_rules, custom_rule_rego=policy.custom_rule_rego if policy else None, org_id=api_key.org_id)
    in_res = in_guard.check(prompt)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    if not in_res.allowed:
        latency_ms = int((time.monotonic() - start) * 1000)
        await _log_request(db, api_key, prompt_hash, prompt[:120], None,
                           model_req or "-", "—", False, in_res.reason, None, None,
                           in_res.reason_code, "input_blocked", latency_ms, 0, 0)
        await db.commit()
        raise HTTPException(status_code=400, detail={"code": in_res.reason_code, "message": in_res.reason})

    call_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if not stream:
        try:
            resp = await call_llm(prompt=prompt, temperature=temperature, max_tokens=max_tokens,
                                  request_model=model_req, org_backend=policy.llm_backend if policy else None,
                                  org_model=policy.llm_model if policy else None)
        except Exception:
            latency_ms = int((time.monotonic() - start) * 1000)
            await _log_request(db, api_key, prompt_hash, prompt[:120], None,
                               model_req or "-", "—", True, None, None, None, None, "error", latency_ms, 0, 0)
            await db.commit()
            raise HTTPException(status_code=502, detail="LLM backend error")
        out_res = OutputGuardrail(out_rules, comp, topic).check(resp.text)
        latency_ms = int((time.monotonic() - start) * 1000)
        status = "delivered" if out_res.allowed else "output_blocked"
        await _log_request(db, api_key, prompt_hash, prompt[:120], None,
                           resp.model, resp.backend, True, None,
                           out_res.allowed, None if out_res.allowed else out_res.reason,
                           None if out_res.allowed else out_res.reason_code,
                           status, latency_ms, resp.input_tokens, resp.output_tokens)
        await db.commit()
        if not out_res.allowed:
            raise HTTPException(status_code=400, detail={"code": out_res.reason_code, "message": out_res.reason})
        return {
            "id": call_id, "object": "chat.completion", "created": created, "model": resp.model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": resp.text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": resp.input_tokens, "completion_tokens": resp.output_tokens,
                      "total_tokens": resp.input_tokens + resp.output_tokens},
        }

    # Streaming SSE in OpenAI chunk format
    async def generate():
        import json as json_lib
        yield f"data: {json_lib.dumps({'id': call_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model_req or 'gateway', 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
        try:
            async for chunk in stream_llm(prompt=prompt, temperature=temperature, max_tokens=max_tokens,
                                          request_model=model_req,
                                          org_backend=policy.llm_backend if policy else None,
                                          org_model=policy.llm_model if policy else None):
                if chunk.done:
                    continue
                yield f"data: {json_lib.dumps({'id': call_id, 'object': 'chat.completion.chunk', 'created': created, 'model': chunk.model, 'choices': [{'index': 0, 'delta': {'content': chunk.token}, 'finish_reason': None}]})}\n\n"
        except Exception:
            pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
