"""
Chat endpoint — the core gateway.
Authenticated via X-Api-Key header (external callers) or JWT (dashboard).

Flow:
  1. Rate limit check
  2. Load org policy
  3. Input guardrail
  4. Call LLM (model-agnostic)
  5. Output guardrail
  6. Log request to DB
  7. Return response
"""
import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, get_sessionmaker
from app.deps import AuthedAPIKey, get_current_user
from app.services.analytics import capture_event
from app.services.vectorstore import upsert_conversation
from app.demo_limits import client_ip, enforce_demo_payload_limits, enforce_demo_rate_limits
from app.middleware.rate_limit import check_rate_limit
from app.models import ChatFeedback, OrgPolicy, RequestLog, User
from app.schemas import ChatRequest, ChatResponse, FeedbackOut, FeedbackRequest, GuardrailResult
from app.services.llm import LLMResponse, call_llm, stream_llm
from app.services.prompt_crypto import encrypt_prompt
from app.services.response_cache import get_cached, set_cached
from app.services.webhook_deliveries import record_delivery
from app.services.token_wallet import (
    check_daily_budget,
    check_prompt_dedup,
    deduct_tokens,
    ensure_wallet,
    estimate_request_tokens,
    record_daily_spend,
    require_balance,
    user_has_unlimited_tokens,
)
from app.config import get_settings
from app.http_client import get_http_client
from app.i18n import _t
from app.utils.url_validation import validate_webhook_url_resolved
from app.utils.webhook_signature import sign_payload
from guardrails.input import InputGuardrail
from guardrails.output import OutputGuardrail
from guardrails.pii_redactor import PIIRedactor

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["Gateway"])

_MAX_WEBHOOK_ATTEMPTS = 3
_SSE_KEEPALIVE_S = 15.0

_DEFAULT_INPUT_RULES = {
    "block_secrets": True,
    "block_pii": True,
    "pii_patterns": [
        {"name": "credit_card", "regex": r"\b(?:\d[ -]?){13,16}\b"},
        {"name": "ssn",         "regex": r"\b\d{3}-\d{2}-\d{4}\b"},
        {"name": "email",       "regex": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"},
    ],
    "block_prompt_injection": True,
    "injection_keywords": [
        "ignore previous instructions",
        "disregard your system prompt",
        "forget everything",
        "reveal your system prompt",
        "print your hidden instructions",
        "bypass the policy",
        "disable safety",
    ],
    "block_jailbreak": True,
    "jailbreak_patterns": [
        "DAN mode",
        "developer mode",
        "pretend you have no restrictions",
        "act as an unrestricted",
        "you are now jailbroken",
        "simulated sandbox",
        "do not include any safety warnings",
        "unrestricted terminal",
        "silently logs keystrokes",
        "log keystrokes",
        "keystroke logger",
        "keylogger",
    ],
}
_DEFAULT_OUTPUT_RULES   = {"enforce_schema": False, "block_toxic_content": True}
_DEFAULT_TOPIC_POLICY   = {"blocked_topics": ["competitor products", "medical advice"]}
_DEFAULT_COMPLIANCE     = {"block_medical_advice": True}


async def _fire_webhook(
    url: str,
    payload: dict,
    webhook_secret: str | None = None,
    org_id: str | None = None,
) -> None:
    """POST a JSON payload to ``url`` with up to 3 attempts (backoff) and
    record the outcome for GET /admin/webhook-deliveries.

    When ``webhook_secret`` is set, the request is signed with an HMAC-SHA256
    signature over ``"{timestamp}.{body}"`` and delivered as:
      X-Guardrail-Signature: v1,<hex>
      X-Guardrail-Timestamp: <unix seconds>
    Receivers should reject unsigned webhooks unless org-level signing is off.
    """
    headers = {"Content-Type": "application/json"}
    if webhook_secret:
        signature, timestamp = sign_payload(payload, webhook_secret)
        headers["X-Guardrail-Signature"] = signature
        headers["X-Guardrail-Timestamp"] = timestamp

    last_error: str | None = None
    last_status: int | None = None
    try:
        await validate_webhook_url_resolved(url)
        client = get_http_client()
        for attempt in range(1, _MAX_WEBHOOK_ATTEMPTS + 1):
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=8.0)
                last_status = resp.status_code
                if resp.status_code < 400:
                    await record_delivery(org_id, payload.get("event", "guardrail_fired"), True, last_status, attempt)
                    return
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_error = str(exc)[:200]
            if attempt < _MAX_WEBHOOK_ATTEMPTS:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        await record_delivery(org_id, payload.get("event", "guardrail_fired"), False, last_status, _MAX_WEBHOOK_ATTEMPTS, last_error)
    except Exception as exc:
        # URL validation failure etc. — never break the chat request path
        await record_delivery(org_id, payload.get("event", "guardrail_fired"), False, None, 0, str(exc)[:200])


def _safe_preview(prompt: str, pii_found: bool) -> str:
    """First 120 chars; redact if PII was detected."""
    preview = prompt[:120]
    return "[REDACTED — PII detected]" if pii_found else preview


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _effective_max_tokens(body: ChatRequest) -> int:
    """
    In demo mode, cap output tokens. The ChatRequest schema defaults max_tokens to
    1024, so we cannot rely on the client omitting the field — always clamp.
    """
    if not settings.DEMO_MODE:
        return body.max_tokens
    if "max_tokens" not in body.model_fields_set:
        return settings.DEMO_MAX_OUTPUT_TOKENS
    return min(body.max_tokens, settings.DEMO_MAX_OUTPUT_TOKENS)


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    api_key: AuthedAPIKey,
    fastapi_response: Response,
    db: AsyncSession = Depends(get_db),
):
    start = time.monotonic()
    request_id = str(uuid.uuid4())

    # ── 1. Scope enforcement ──────────────────────────────────────────────
    key_scopes = list(api_key.scopes) if api_key.scopes else ["chat"]
    if "chat" not in key_scopes:
        raise HTTPException(status_code=403, detail=_t("api_key.no_chat_scope"))

    # ── 2. Load org policy ────────────────────────────────────────────────
    policy: OrgPolicy | None = None
    if api_key.org_id:
        result = await db.execute(
            select(OrgPolicy).where(OrgPolicy.org_id == api_key.org_id)
        )
        policy = result.scalar_one_or_none()

    input_rules      = policy.input_rules      if policy else _DEFAULT_INPUT_RULES
    output_rules     = policy.output_rules     if policy else _DEFAULT_OUTPUT_RULES
    topic_policy     = policy.topic_policy     if policy else _DEFAULT_TOPIC_POLICY
    compliance_rules = policy.compliance_rules if policy else _DEFAULT_COMPLIANCE
    org_backend      = policy.llm_backend      if policy else None
    org_model        = policy.llm_model        if policy else None
    rpm = (policy.rate_limit_rpm if policy and policy.rate_limit_rpm else None) or settings.DEFAULT_RATE_LIMIT_RPM
    rpd = (policy.rate_limit_rpd if policy and policy.rate_limit_rpd else None) or settings.DEFAULT_RATE_LIMIT_RPD

    # ── 3. IP blocklist ───────────────────────────────────────────────────
    blocked_ips = compliance_rules.get("blocked_ips", [])
    if blocked_ips:
        req_ip = client_ip(request)
        if req_ip in blocked_ips:
            raise HTTPException(status_code=403, detail=_t("chat.ip_blocked"))

    # PII redaction mode: "block" (default), "redact", or "off"
    pii_mode = input_rules.get("pii_redaction_mode", "block")

    max_tokens = _effective_max_tokens(body)
    enforce_demo_payload_limits(body.prompt, max_tokens)

    # ── 4. Prompt dedup (same prompt = likely a bot) ─────────────────────────
    prompt_hash = _sha256(body.prompt)
    await check_prompt_dedup(api_key.owner_id, prompt_hash)

    # ── 5. Daily budget ─────────────────────────────────────────────────────
    estimated = estimate_request_tokens(body.prompt, max_tokens)
    check_daily_budget(api_key.owner_id, estimated)

    # ── 6. Token balance (billing) ───────────────────────────────────────────
    wallet = await require_balance(db, api_key.owner_id, estimated)

    # ── 7. Rate limit ─────────────────────────────────────────────────────
    try:
        rate_info = await check_rate_limit(api_key.id, rpm, rpd)
        await check_rate_limit(f"user:{api_key.owner_id}", rpm, rpd)
        await enforce_demo_rate_limits(api_key.id, client_ip(request))
    except HTTPException as e:
        if e.status_code != 429:
            raise
        latency_ms = int((time.monotonic() - start) * 1000)
        await _log_request(
            db=db, api_key=api_key,
            prompt_hash=_sha256(body.prompt),
            prompt_preview=_safe_preview(body.prompt, False),
            full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
            model=body.model or "-", backend=body.backend or settings.DEFAULT_LLM_BACKEND,
            input_passed=True, input_block_reason=None,
            output_passed=None, output_block_reason=None,
            fired_rule="rate_limit",
            status="rate_limited", latency_ms=latency_ms,
            input_tokens=0, output_tokens=0,
        )
        await db.commit()
        raise

    if fastapi_response is not None and rate_info is not None:
        fastapi_response.headers["X-RateLimit-Limit"] = str(rpm)
        fastapi_response.headers["X-RateLimit-Remaining"] = str(rate_info["rpm_remaining"])
        if rpd < 1_000_000:
            fastapi_response.headers["X-RateLimit-Limit-Day"] = str(rpd)
            fastapi_response.headers["X-RateLimit-Remaining-Day"] = str(rate_info.get("rpd_remaining", rpd))

    # ── 8. PII Redaction (if mode == "redact") ────────────────────────────
    redaction_result = None
    prompt_for_llm = body.prompt

    if pii_mode == "redact":
        redactor = PIIRedactor(
            extra_patterns=input_rules.get("pii_patterns")
        )
        redaction_result = redactor.redact(body.prompt)
        prompt_for_llm = redaction_result.redacted_text

    # ── 9. Input guardrail ───────────────────────────────────────────────
    # When in "redact" mode, skip the PII check (we already handled it)
    guardrail_rules = dict(input_rules)
    if pii_mode == "redact":
        guardrail_rules["block_pii"] = False

    in_guard = InputGuardrail(guardrail_rules)
    in_result = in_guard.check(prompt_for_llm)

    pii_found = (redaction_result is not None and redaction_result.pii_found)

    if not in_result.allowed:
        latency_ms = int((time.monotonic() - start) * 1000)
        capture_event(api_key.owner_id, "guardrail_blocked", {
            "direction": "input", "reason": in_result.reason_code,
            "backend": body.backend or settings.DEFAULT_LLM_BACKEND,
            "model": body.model or org_model or settings.DEFAULT_MODEL,
        })
        await _log_request(
            db=db, api_key=api_key,
            prompt_hash=_sha256(body.prompt),
            prompt_preview=_safe_preview(body.prompt, pii_found),
            full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
            model="—", backend="—",
            input_passed=False, input_block_reason=in_result.reason,
            output_passed=None, output_block_reason=None,
            fired_rule=in_result.reason_code,
            status="input_blocked", latency_ms=latency_ms,
            input_tokens=0, output_tokens=0,
        )
        await db.commit()
        webhook_url = compliance_rules.get("webhook_url")
        if webhook_url:
            asyncio.create_task(_fire_webhook(webhook_url, {
                "event": "guardrail_fired", "status": "input_blocked",
                "fired_rule": in_result.reason_code, "reason": in_result.reason or "",
                "prompt_preview": _safe_preview(body.prompt, pii_found),
                "latency_ms": latency_ms,
            }, webhook_secret=compliance_rules.get("webhook_secret"), org_id=api_key.org_id))
        bal = (await ensure_wallet(db, api_key.owner_id)).balance_tokens
        return ChatResponse(
            request_id=request_id,
            response=None,
            status="input_blocked",
            input_guard=GuardrailResult(
                passed=False,
                check=in_result.check,
                reason=in_result.reason or "",
                reason_code=in_result.reason_code,
                risk_score=in_result.risk_score,
            ),
            output_guard=None,
            latency_ms=latency_ms,
            model="—", backend="—",
            tokens_remaining=bal if settings.BILLING_ENABLED else None,
        )

    # ── 10. Call LLM (with redacted prompt if applicable) ─────────────────
    llm_backend = body.backend or org_backend or settings.DEFAULT_LLM_BACKEND
    llm_model   = body.model   or org_model   or settings.DEFAULT_MODEL
    use_cache = settings.RESPONSE_CACHE_ENABLED and bool(output_rules.get("response_cache"))
    fallbacks = compliance_rules.get("llm_fallbacks")  # litellm provider failover
    try:
        cached_text = None
        if use_cache:
            cached_text = await get_cached(prompt_for_llm, llm_model, body.temperature)
        if cached_text is not None:
            llm_resp = LLMResponse(
                text=cached_text, input_tokens=0, output_tokens=0,
                model=llm_model, backend=llm_backend,
            )
        else:
            llm_resp = await call_llm(
                prompt=prompt_for_llm,
                temperature=body.temperature,
                max_tokens=max_tokens,
                request_backend=body.backend,
                org_backend=org_backend,
                request_model=body.model,
                org_model=org_model,
                fallbacks=fallbacks,
                cache=use_cache,
            )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        await _log_request(
            db=db, api_key=api_key,
            prompt_hash=_sha256(body.prompt),
            prompt_preview=_safe_preview(body.prompt, False),
            full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
            model=body.model or "—", backend=body.backend or settings.DEFAULT_LLM_BACKEND,
            input_passed=True, input_block_reason=None,
            output_passed=None, output_block_reason=None,
            fired_rule=None,
            status="error", latency_ms=latency_ms,
            input_tokens=0, output_tokens=0,
        )
        raise HTTPException(status_code=502, detail=_t("chat.llm_error"))

    # ── 11. Output guardrail ───────────────────────────────────────────────
    if redaction_result and redaction_result.mapping:
        llm_resp.text = redactor.restore(llm_resp.text, redaction_result.mapping)
    out_guard = OutputGuardrail(output_rules, compliance_rules, topic_policy)
    out_result = out_guard.check(llm_resp.text)

    latency_ms = int((time.monotonic() - start) * 1000)
    status_str = "delivered" if out_result.allowed else "output_blocked"

    # Cache only fully-delivered responses (opt-in per policy)
    if use_cache and out_result.allowed:
        await set_cached(prompt_for_llm, llm_model, body.temperature, llm_resp.text)

    # Log fired_rule for warnings even when request is delivered through
    fired_rule = None
    if not out_result.allowed:
        fired_rule = out_result.reason_code
    elif out_result.warned:
        fired_rule = out_result.reason_code
    elif in_result.warned:
        fired_rule = in_result.reason_code

    await _log_request(
        db=db, api_key=api_key,
        prompt_hash=_sha256(body.prompt),
        prompt_preview=_safe_preview(body.prompt, False),
        full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
        model=llm_resp.model, backend=llm_resp.backend,
        input_passed=True, input_block_reason=None,
        output_passed=out_result.allowed,
        output_block_reason=None if out_result.allowed else out_result.reason,
        fired_rule=fired_rule,
        status=status_str, latency_ms=latency_ms,
        input_tokens=llm_resp.input_tokens, output_tokens=llm_resp.output_tokens,
    )

    used = llm_resp.input_tokens + llm_resp.output_tokens
    await deduct_tokens(db, wallet, used)
    record_daily_spend(api_key.owner_id, used)
    await db.commit()
    await upsert_conversation(
        session_id=api_key.id,
        prompt=body.prompt,
        response=llm_resp.text if out_result.allowed else None,
        status=status_str,
        metadata={"org_id": api_key.org_id, "backend": llm_resp.backend, "model": llm_resp.model},
    )
    if not out_result.allowed:
        capture_event(api_key.owner_id, "guardrail_blocked", {
            "direction": "output", "reason": out_result.reason_code,
            "backend": llm_resp.backend, "model": llm_resp.model,
        })
        webhook_url = compliance_rules.get("webhook_url")
        if webhook_url:
            asyncio.create_task(_fire_webhook(webhook_url, {
                "event": "guardrail_fired", "status": "output_blocked",
                "fired_rule": out_result.reason_code, "reason": out_result.reason or "",
                "prompt_preview": _safe_preview(body.prompt, False),
                "latency_ms": latency_ms,
            }, webhook_secret=compliance_rules.get("webhook_secret"), org_id=api_key.org_id))
    unlimited = await user_has_unlimited_tokens(db, api_key.owner_id)
    bal = wallet.balance_tokens

    # If we redacted PII, report it in the input guard reason
    if redaction_result and redaction_result.pii_found:
        in_reason = f"PII redacted: {', '.join(redaction_result.pii_types)} ({redaction_result.pii_count} items)"
    else:
        in_reason = in_result.reason or ""

    return ChatResponse(
        request_id=request_id,
        response=llm_resp.text if out_result.allowed else None,
        status=status_str,
        input_guard=GuardrailResult(
            passed=True,
            check="PII Redaction + Input Checks" if pii_found else in_result.check,
            reason=in_reason,
            reason_code="pii_redacted" if pii_found else in_result.reason_code,
            risk_score=0.4 if pii_found else in_result.risk_score,
        ),
        output_guard=GuardrailResult(
            passed=out_result.allowed,
            check=out_result.check,
            reason=out_result.reason or "",
            reason_code=out_result.reason_code,
            risk_score=out_result.risk_score,
        ),
        latency_ms=latency_ms,
        model=llm_resp.model,
        backend=llm_resp.backend,
        tokens_remaining=bal if settings.BILLING_ENABLED and not unlimited else None,
    )


@router.post("/stream", tags=["Gateway"])
async def chat_stream(
    body: ChatRequest,
    request: Request,
    api_key: AuthedAPIKey,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming endpoint. Yields `data: {json}` events:
      {"type":"token",  "content":"..."}            — each LLM token
      {"type":"done",   "status":"delivered", ...}  — final metadata
      {"type":"blocked","status":"input_blocked"|"output_blocked", ...}
      {"type":"error",  "detail":"..."}             — backend failure
      {"type":"ping"}                               — keepalive every 15s
    """
    start = time.monotonic()
    request_id = str(uuid.uuid4())

    # ── Scope enforcement ─────────────────────────────────────────────────
    key_scopes = list(api_key.scopes) if api_key.scopes else ["chat"]
    if "chat" not in key_scopes:
        raise HTTPException(status_code=403, detail=_t("api_key.no_chat_scope"))

    # ── Load policy ───────────────────────────────────────────────────────
    policy: OrgPolicy | None = None
    if api_key.org_id:
        result = await db.execute(select(OrgPolicy).where(OrgPolicy.org_id == api_key.org_id))
        policy = result.scalar_one_or_none()

    input_rules      = policy.input_rules      if policy else _DEFAULT_INPUT_RULES
    output_rules     = policy.output_rules     if policy else _DEFAULT_OUTPUT_RULES
    topic_policy     = policy.topic_policy     if policy else _DEFAULT_TOPIC_POLICY
    compliance_rules = policy.compliance_rules if policy else _DEFAULT_COMPLIANCE
    org_backend      = policy.llm_backend      if policy else None
    org_model        = policy.llm_model        if policy else None
    rpm = (policy.rate_limit_rpm if policy and policy.rate_limit_rpm else None) or settings.DEFAULT_RATE_LIMIT_RPM
    rpd = (policy.rate_limit_rpd if policy and policy.rate_limit_rpd else None) or settings.DEFAULT_RATE_LIMIT_RPD

    # ── IP blocklist ──────────────────────────────────────────────────────
    blocked_ips = compliance_rules.get("blocked_ips", [])
    if blocked_ips:
        req_ip = client_ip(request)
        if req_ip in blocked_ips:
            raise HTTPException(status_code=403, detail=_t("chat.ip_blocked"))

    pii_mode   = input_rules.get("pii_redaction_mode", "block")
    max_tokens = _effective_max_tokens(body)
    enforce_demo_payload_limits(body.prompt, max_tokens)

    # ── Prompt dedup ─────────────────────────────────────────────────────────
    await check_prompt_dedup(api_key.owner_id, _sha256(body.prompt))

    # ── Daily budget ─────────────────────────────────────────────────────────
    stream_estimated = estimate_request_tokens(body.prompt, max_tokens)
    check_daily_budget(api_key.owner_id, stream_estimated)

    # ── Rate limit (before stream starts so we can return HTTP 429) ───────
    try:
        stream_rate_info = await check_rate_limit(api_key.id, rpm, rpd)
        await check_rate_limit(f"user:{api_key.owner_id}", rpm, rpd)
        await enforce_demo_rate_limits(api_key.id, client_ip(request))
    except HTTPException:
        raise

    # ── Token balance ─────────────────────────────────────────────────────
    wallet = await require_balance(db, api_key.owner_id, stream_estimated)

    # ── PII redaction ─────────────────────────────────────────────────────
    redaction_result = None
    prompt_for_llm   = body.prompt
    if pii_mode == "redact":
        redactor = PIIRedactor(extra_patterns=input_rules.get("pii_patterns"))
        redaction_result = redactor.redact(body.prompt)
        prompt_for_llm   = redaction_result.redacted_text

    # ── Input guardrail ───────────────────────────────────────────────────
    guardrail_rules = dict(input_rules)
    if pii_mode == "redact":
        guardrail_rules["block_pii"] = False
    in_guard  = InputGuardrail(guardrail_rules)
    in_result = in_guard.check(prompt_for_llm)
    pii_found = redaction_result is not None and redaction_result.pii_found

    def _sse(payload: dict) -> str:
        return f"data: {json_lib.dumps(payload)}\n\n"

    async def generate():
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as stream_db:
            from sqlalchemy import select
            from app.models import TokenWallet
            stream_wallet = await stream_db.execute(
                select(TokenWallet).where(TokenWallet.user_id == api_key.owner_id)
            )
            stream_wallet = stream_wallet.scalar_one()
            try:
                if not in_result.allowed:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    capture_event(api_key.owner_id, "guardrail_blocked", {
                        "direction": "input", "reason": in_result.reason_code,
                        "backend": body.backend or settings.DEFAULT_LLM_BACKEND,
                        "model": body.model or org_model or settings.DEFAULT_MODEL,
                    })
                    await _log_request(
                        db=stream_db, api_key=api_key,
                        prompt_hash=_sha256(body.prompt),
                        prompt_preview=_safe_preview(body.prompt, pii_found),
                        full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
                        model="—", backend="—",
                        input_passed=False, input_block_reason=in_result.reason,
                        output_passed=None, output_block_reason=None,
                        fired_rule=in_result.reason_code,
                        status="input_blocked", latency_ms=latency_ms,
                        input_tokens=0, output_tokens=0,
                    )
                    await stream_db.commit()
                    webhook_url = compliance_rules.get("webhook_url")
                    if webhook_url:
                        asyncio.create_task(_fire_webhook(webhook_url, {
                            "event": "guardrail_fired", "status": "input_blocked",
                            "fired_rule": in_result.reason_code, "reason": in_result.reason or "",
                            "prompt_preview": _safe_preview(body.prompt, pii_found),
                            "latency_ms": latency_ms,
                        }, webhook_secret=compliance_rules.get("webhook_secret"), org_id=api_key.org_id))
                    yield _sse({
                        "type": "blocked", "request_id": request_id,
                        "status": "input_blocked",
                        "input_guard": {
                            "passed": False, "check": in_result.check,
                            "reason": in_result.reason or "",
                            "reason_code": in_result.reason_code,
                            "risk_score": in_result.risk_score,
                        },
                    })
                    return

                # ── Stream from LLM ───────────────────────────────────────────────
                accumulated: list[str] = []
                input_tokens = output_tokens = 0
                llm_model   = body.model   or org_model   or settings.DEFAULT_MODEL
                llm_backend = body.backend or org_backend or settings.DEFAULT_LLM_BACKEND

                try:
                    stream_iter = stream_llm(
                        prompt=prompt_for_llm, temperature=body.temperature,
                        max_tokens=max_tokens,
                        request_backend=body.backend, org_backend=org_backend,
                        request_model=body.model,    org_model=org_model,
                        fallbacks=compliance_rules.get("llm_fallbacks"),
                        cache=settings.RESPONSE_CACHE_ENABLED and bool(output_rules.get("response_cache")),
                    ).__aiter__()
                    while True:
                        try:
                            chunk = await asyncio.wait_for(anext(stream_iter), timeout=_SSE_KEEPALIVE_S)
                        except asyncio.TimeoutError:
                            # keep the SSE connection alive during long generations
                            yield _sse({"type": "ping"})
                            continue
                        if chunk.done:
                            input_tokens = chunk.input_tokens
                            output_tokens = chunk.output_tokens
                            llm_model   = chunk.model
                            llm_backend = chunk.backend
                        else:
                            accumulated.append(chunk.token)
                            yield _sse({"type": "token", "content": chunk.token})
                except StopAsyncIteration:
                    pass
                except Exception as e:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    await _log_request(
                        db=stream_db, api_key=api_key,
                        prompt_hash=_sha256(body.prompt),
                        prompt_preview=_safe_preview(body.prompt, False),
                        full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
                        model=llm_model, backend=llm_backend,
                        input_passed=True, input_block_reason=None,
                        output_passed=None, output_block_reason=None,
                        fired_rule=None, status="error", latency_ms=latency_ms,
                        input_tokens=0, output_tokens=0,
                    )
                    await stream_db.commit()
                    yield _sse({"type": "error", "status": "error", "detail": _t("chat.llm_error")})
                    return

                # ── Output guardrail (on full accumulated text) ───────────────────
                full_response = "".join(accumulated)
                if redaction_result and redaction_result.mapping:
                    full_response = redactor.restore(full_response, redaction_result.mapping)
                out_guard  = OutputGuardrail(output_rules, compliance_rules, topic_policy)
                out_result = out_guard.check(full_response)

                latency_ms = int((time.monotonic() - start) * 1000)
                status_str = "delivered" if out_result.allowed else "output_blocked"

                fired_rule = None
                if not out_result.allowed:
                    fired_rule = out_result.reason_code
                elif out_result.warned or in_result.warned:
                    fired_rule = out_result.reason_code if out_result.warned else in_result.reason_code

                await _log_request(
                    db=stream_db, api_key=api_key,
                    prompt_hash=_sha256(body.prompt),
                    prompt_preview=_safe_preview(body.prompt, pii_found),
                    full_prompt=body.prompt if compliance_rules.get("full_prompt_logging") else None,
                    model=llm_model, backend=llm_backend,
                    input_passed=True, input_block_reason=None,
                    output_passed=out_result.allowed,
                    output_block_reason=None if out_result.allowed else out_result.reason,
                    fired_rule=fired_rule, status=status_str, latency_ms=latency_ms,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                )
                used = input_tokens + output_tokens
                await deduct_tokens(stream_db, stream_wallet, used)
                record_daily_spend(api_key.owner_id, used)
                await stream_db.commit()
                await upsert_conversation(
                    session_id=api_key.id,
                    prompt=body.prompt,
                    response=full_response if out_result.allowed else None,
                    status=status_str,
                    metadata={"org_id": api_key.org_id, "backend": llm_backend, "model": llm_model},
                )
                if not out_result.allowed:
                    capture_event(api_key.owner_id, "guardrail_blocked", {
                        "direction": "output", "reason": out_result.reason_code,
                        "backend": llm_backend, "model": llm_model,
                    })
                    webhook_url = compliance_rules.get("webhook_url")
                    if webhook_url:
                        asyncio.create_task(_fire_webhook(webhook_url, {
                            "event": "guardrail_fired", "status": "output_blocked",
                            "fired_rule": out_result.reason_code, "reason": out_result.reason or "",
                            "prompt_preview": _safe_preview(body.prompt, pii_found),
                            "latency_ms": latency_ms,
                        }, webhook_secret=compliance_rules.get("webhook_secret"), org_id=api_key.org_id))
            finally:
                await stream_db.close()

        if pii_found:
            in_reason = f"PII redacted: {', '.join(redaction_result.pii_types)} ({redaction_result.pii_count} items)"
        else:
            in_reason = in_result.reason or ""

        yield _sse({
            "type": "output_blocked" if not out_result.allowed else "done",
            "request_id": request_id,
            "status": status_str,
            "model": llm_model, "backend": llm_backend,
            "latency_ms": latency_ms,
            "input_guard": {
                "passed": True,
                "check": "PII Redaction + Input Checks" if pii_found else in_result.check,
                "reason": in_reason,
                "reason_code": "pii_redacted" if pii_found else in_result.reason_code,
                "risk_score": 0.4 if pii_found else in_result.risk_score,
            },
            "output_guard": {
                "passed": out_result.allowed,
                "check": out_result.check,
                "reason": out_result.reason or "",
                "reason_code": out_result.reason_code,
                "risk_score": out_result.risk_score,
            },
        })

    stream_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    if stream_rate_info is not None:
        stream_headers["X-RateLimit-Limit"] = str(rpm)
        stream_headers["X-RateLimit-Remaining"] = str(stream_rate_info["rpm_remaining"])
        if rpd < 1_000_000:
            stream_headers["X-RateLimit-Limit-Day"] = str(rpd)
            stream_headers["X-RateLimit-Remaining-Day"] = str(stream_rate_info.get("rpd_remaining", rpd))
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=stream_headers,
    )


async def _log_request(
    db, api_key, prompt_hash, prompt_preview, full_prompt,
    model, backend, input_passed, input_block_reason,
    output_passed, output_block_reason, fired_rule,
    status, latency_ms, input_tokens, output_tokens,
):
    log = RequestLog(
        api_key_id=api_key.id,
        org_id=api_key.org_id,
        prompt_hash=prompt_hash,
        prompt_preview=prompt_preview,
        full_prompt=encrypt_prompt(full_prompt) if full_prompt else None,
        model=model, backend=backend,
        input_passed=input_passed,
        input_block_reason=input_block_reason,
        output_passed=output_passed,
        output_block_reason=output_block_reason,
        fired_rule=fired_rule,
        status=status,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(log)

    # Update counters on the API key (non-blocking)
    api_key.total_requests += 1
    if status != "delivered":
        api_key.total_blocked += 1
    api_key.total_tokens += input_tokens + output_tokens
    api_key.last_used_at = datetime.now(timezone.utc)

    await db.flush()


@router.post("/{request_id}/feedback", status_code=201)
async def submit_feedback(
    request_id: str,
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    log = await db.get(RequestLog, request_id)
    if not log:
        raise HTTPException(status_code=404, detail=_t("chat.feedback_not_found"))

    existing = await db.execute(
        select(ChatFeedback).where(ChatFeedback.request_log_id == request_id)
    )
    existing_fb = existing.scalar_one_or_none()

    if existing_fb:
        existing_fb.rating = body.rating
        existing_fb.comment = body.comment
    else:
        fb = ChatFeedback(
            request_log_id=request_id,
            user_id=user.id,
            rating=body.rating,
            comment=body.comment,
        )
        db.add(fb)

    await db.flush()
    return FeedbackOut.model_validate(existing_fb or fb)
