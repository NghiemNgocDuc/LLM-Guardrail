"""Correlation ID propagation — X-Request-ID / X-Correlation-ID end-to-end."""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Request-ID"] = cid
        return response
