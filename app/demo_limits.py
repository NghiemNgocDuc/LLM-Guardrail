from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.middleware.rate_limit import check_rate_limit

settings = get_settings()


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_demo_payload_limits(prompt: str, max_tokens: int) -> None:
    if not settings.DEMO_MODE:
        return

    if len(prompt) > settings.DEMO_MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Demo limit exceeded: prompt must be {settings.DEMO_MAX_PROMPT_CHARS} characters or fewer.",
        )

    if max_tokens > settings.DEMO_MAX_OUTPUT_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Demo limit exceeded: max_tokens must be {settings.DEMO_MAX_OUTPUT_TOKENS} or fewer.",
        )


async def enforce_demo_rate_limits(api_key_id: str, ip_address: str) -> None:
    if not settings.DEMO_MODE:
        return

    await check_rate_limit(
        f"demo:user:{api_key_id}",
        settings.DEMO_RATE_LIMIT_RPM,
        settings.DEMO_RATE_LIMIT_RPD,
    )
    await check_rate_limit(
        f"demo:ip:{ip_address}",
        settings.DEMO_IP_RATE_LIMIT_RPM,
        settings.DEMO_IP_RATE_LIMIT_RPD,
    )
