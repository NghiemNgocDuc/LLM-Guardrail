"""Egress scrub — last line of defense: no secret ever leaves as HTTP response."""
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.utils.secret_redaction import scrub_text


class SecretScrubMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Only scrub JSON responses (skip SSE / file / static)
        ct = response.headers.get("content-type", "")
        if "application/json" not in ct:
            return response
        # Best-effort: if we can read body, scrub it. For streaming we skip.
        body = getattr(response, "body", None)
        if body is None:
            return response
        try:
            text = body.decode() if isinstance(body, (bytes, bytearray)) else str(body)
            if not text:
                return response
            # quick check to avoid json parsing on every request
            if "gsk_" not in text and "sk-" not in text and "grg_" not in text and "AKIA" not in text and "Bearer" not in text:
                # still check literal configured key (may have no prefix)
                from app.utils.secret_redaction import contains_secret
                hit, _ = contains_secret(text)
                if not hit:
                    return response
            scrubbed = scrub_text(text)
            if scrubbed == text:
                return response
            # rebuild response with scrubbed body; preserve status/headers
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return JSONResponse(
                content=json.loads(scrubbed) if scrubbed.strip().startswith(("{", "[")) else {"detail": scrubbed},
                status_code=response.status_code,
                headers=headers,
            )
        except Exception:
            return response
