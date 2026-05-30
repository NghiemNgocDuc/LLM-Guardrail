from urllib.parse import urlparse

from app.config import get_settings


def _mask_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return "<missing>"
    host = parsed.hostname or "<missing-host>"
    return f"{parsed.scheme}://<credentials>@{host}:{parsed.port or ''}{parsed.path}"


def main() -> None:
    settings = get_settings()
    print("startup.preflight=ok", flush=True)
    print(f"app_env={settings.APP_ENV}", flush=True)
    print(f"default_llm_backend={settings.DEFAULT_LLM_BACKEND}", flush=True)
    print(f"database_url={_mask_url(settings.DATABASE_URL)}", flush=True)
    print(f"rate_limit_redis_url={_mask_url(settings.RATE_LIMIT_REDIS_URL)}", flush=True)
    print(f"groq_api_key_configured={bool(settings.GROQ_API_KEY)}", flush=True)
    print(f"allowed_origins={settings.ALLOWED_ORIGINS}", flush=True)


if __name__ == "__main__":
    main()
