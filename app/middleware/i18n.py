"""Per-request language from Accept-Language header."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.i18n import set_language


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        header = request.headers.get("accept-language", "")
        if header:
            set_language(header)
        return await call_next(request)
