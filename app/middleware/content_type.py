"""Content-Type enforcement — reject POST/PUT/PATCH without JSON body."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class ContentTypeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        if method in ("POST", "PUT", "PATCH") and not path.startswith(("/health", "/robots", "/.well-known", "/auth/clerk-webhook")):
            ct = request.headers.get("content-type", "")
            if not ct.startswith("application/json"):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=415,
                    content={"detail": "Content-Type must be application/json"},
                )

        return await call_next(request)
