import json
import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("app.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.monotonic()

        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            status_code = response.status_code if response else 500
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "latency_ms": latency_ms,
                        "client_ip": request.client.host if request.client else "unknown",
                    },
                    separators=(",", ":"),
                )
            )
            if response:
                response.headers["X-Request-ID"] = request_id
