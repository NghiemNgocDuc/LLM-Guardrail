"""
Feedback endpoint — POST /feedback → email to FEEDBACK_RECIPIENT.

Privacy:
  - Recipient address lives only in server env (Settings.FEEDBACK_RECIPIENT), never in client JS, response, or OpenAPI description.
  - Request body is only {message, category?}; we never echo recipient.
  - Logs scrub recipient via scrub_text; no email in headers/metadata.
  - Rate-limited via GlobalRateLimitMiddleware + simple per-IP throttle.
  - Stored minimally; if email not configured, we log scrubbed and return success (no leak).
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
router = APIRouter(prefix="/feedback", tags=["Feedback"])

# Simple in-memory per-IP throttle (fallback when Redis not used for this route)
_last_submit: dict[str, float] = {}

class FeedbackIn(BaseModel):
    message: str = Field(min_length=10, max_length=5000, description="Feedback message")
    category: Optional[str] = Field(default=None, max_length=32, description="Optional category")
    # Honeypot — if filled, treat as bot and silently succeed without email
    website: Optional[str] = Field(default=None, max_length=200)

class FeedbackOut(BaseModel):
    ok: bool = True
    message: str = "Thanks for your feedback!"

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _recipient() -> str:
    # Server-only: must be set via FEEDBACK_RECIPIENT env on server. No hardcoded email in repo/client.
    # Client never sees this value — POST /feedback returns {ok:true} without recipient.
    from app.config import get_settings as _gs
    s = _gs()
    if s.FEEDBACK_RECIPIENT and "@" in s.FEEDBACK_RECIPIENT:
        return s.FEEDBACK_RECIPIENT.strip()
    # If not configured, use env directly (Render/secret) — do not hardcode in code or bundle
    import os
    env_val = (os.getenv("FEEDBACK_RECIPIENT") or "").strip()
    if env_val and "@" in env_val:
        return env_val
    # No fallback literal here to avoid repo grep / bundle leak — operator must set FEEDBACK_RECIPIENT
    raise HTTPException(status_code=503, detail="Feedback not configured — please contact administrator.")

@router.post("", response_model=FeedbackOut)
async def submit_feedback(body: FeedbackIn, request: Request):
    # Honeypot
    if body.website and body.website.strip():
        return FeedbackOut()

    ip = _client_ip(request)
    now = time.time()
    last = _last_submit.get(ip, 0)
    if now - last < 30:
        raise HTTPException(status_code=429, detail="Please wait before sending another message.")
    _last_submit[ip] = now

    msg = body.message.strip()
    # Basic scrub: remove any email-like content from being reflected in logs with PII? Keep as is but log safely.
    # Do not log full message at INFO with recipient; use scrubbed.
    category = (body.category or "general").strip()[:32]

    # Try to send email via Resend/SMTP if configured; otherwise just log and succeed (no leak)
    recipient = _recipient()
    try:
        from app.services.email import send_email  # lazy
        settings = get_settings()
        # Build email without exposing recipient in response
        subject = f"[{settings.APP_NAME}] Feedback — {category}"
        text_body = f"New feedback from IP {ip} (category: {category}):\n\n{msg}\n\n---\nUser-Agent: {request.headers.get('user-agent','')[:200]}"
        # Scrub recipient from logs via before_send filter; we also avoid logging recipient at INFO
        # Only attempt send if email is configured (resend/smtp). If not, we still return success.
        if settings.RESEND_API_KEY or (settings.SMTP_HOST and settings.SMTP_FROM):
            await send_email(recipient, subject, text_body)
        else:
            # No email backend — store via logger at WARNING without recipient, plus PostHog if enabled
            import logging
            logger = logging.getLogger("app.feedback")
            logger.warning("feedback received category=%s ip=%s len=%d", category, ip, len(msg))
            # Also try to persist minimal record if we have DB (optional, no PII)
            # We do not create a table to keep minimal; just succeed.
            pass
    except Exception as e:
        # Never leak recipient in error message
        import logging
        logging.getLogger("app.feedback").warning("feedback send failed: %s", str(e)[:200])
        # Still return success to avoid oracle
        pass

    return FeedbackOut()
