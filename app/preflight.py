import urllib.request
from urllib.parse import urlparse

from app.config import get_settings


def _mask_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return "<missing>"
    host = parsed.hostname or "<missing-host>"
    return f"{parsed.scheme}://<credentials>@{host}:{parsed.port or ''}{parsed.path}"


def _check_ollama(base_url: str) -> str:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as r:
            return "reachable" if r.status == 200 else f"http_{r.status}"
    except Exception as e:
        return f"unreachable ({e})"


def main() -> None:
    settings = get_settings()
    print("startup.preflight=ok", flush=True)
    print(f"app_env={settings.APP_ENV}", flush=True)
    print(f"default_llm_backend={settings.DEFAULT_LLM_BACKEND}", flush=True)
    print(f"database_url={_mask_url(settings.DATABASE_URL)}", flush=True)
    print(f"rate_limit_redis_url={_mask_url(settings.RATE_LIMIT_REDIS_URL)}", flush=True)
    print(f"groq_api_key_configured={bool(settings.GROQ_API_KEY)}", flush=True)
    print(f"ollama_url={settings.OLLAMA_BASE_URL}", flush=True)
    if settings.DEFAULT_LLM_BACKEND == "ollama":
        print(f"ollama_status={_check_ollama(settings.OLLAMA_BASE_URL)}", flush=True)
    print(f"email_configured={settings.email_configured} provider={'resend' if settings.RESEND_API_KEY else 'smtp' if settings.SMTP_HOST and settings.SMTP_FROM else 'none'}", flush=True)
    print(f"require_email_verification={settings.REQUIRE_EMAIL_VERIFICATION}", flush=True)
    print(f"demo_max_output_tokens={settings.DEMO_MAX_OUTPUT_TOKENS}", flush=True)
    print(f"allowed_origins={settings.ALLOWED_ORIGINS}", flush=True)


if __name__ == "__main__":
    main()
