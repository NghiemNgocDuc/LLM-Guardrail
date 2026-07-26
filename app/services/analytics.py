"""Server-side analytics via PostHog (call from routers when key events happen)."""
import logging

import posthog

from app.config import get_settings

logger = logging.getLogger(__name__)


def capture_event(user_id: str, event: str, properties: dict | None = None) -> None:
    settings = get_settings()
    if not settings.POSTHOG_API_KEY:
        return
    try:
        posthog.capture(
            distinct_id=user_id,
            event=event,
            properties=properties or {},
        )
    except Exception:
        logger.exception("analytics.capture_failed event=%s", event)


def capture_guardrail_block(user_id: str, direction: str, reason: str, backend: str, model: str) -> None:
    capture_event(user_id, "guardrail_blocked", {
        "direction": direction,
        "reason": reason,
        "backend": backend,
        "model": model,
    })
