from functools import lru_cache
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_NAME: str = "LLM Guardrails Gateway"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""

    POSTHOG_API_KEY: str = ""
    POSTHOG_HOST: str = "https://us.i.posthog.com"

    PRODUCTBRIDGE_API_KEY: str = ""

    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = ""
    PINECONE_INDEX_NAME: str = "guardrails"
    # When False, conversation text is NOT sent to Pinecone (embedding vectors
    # used for similarity search are generated on-the-fly without persistence).
    # Set to True only if you explicitly need conversation history for RAG.
    PINECONE_STORE_CONVERSATIONS: bool = False

    ALLOWED_ORIGINS: str = "http://localhost:8080,http://localhost:5173"

    DATABASE_URL: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Public URL of the dashboard (used in email links), e.g. https://your-app.onrender.com
    PUBLIC_APP_URL: str = "http://localhost:8080"
    REQUIRE_EMAIL_VERIFICATION: bool = True
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_HOURS: int = 1

    # Clerk (replaces email/password auth — https://clerk.com)
    CLERK_SECRET_KEY: str = ""           # Clerk API key (server-side operations)
    CLERK_JWKS_URL: str = ""             # e.g. https://your-app.clerk.accounts.dev/.well-known/jwks.json
    CLERK_JWT_KEY: str = ""              # PEM public key — if set, JWT verification is networkless (no JWKS fetch)
    CLERK_WEBHOOK_SECRET: str = ""       # Svix signing secret for webhook verification

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    RESEND_API_KEY: str = ""
    RESEND_FROM: str = ""

    DEFAULT_RATE_LIMIT_RPM: int = 60
    DEFAULT_RATE_LIMIT_RPD: int = 1000
    RATE_LIMIT_REDIS_URL: str = ""

    DEMO_MODE: bool = False
    DEMO_DISABLE_SIGNUPS: bool = False
    DEMO_RATE_LIMIT_RPM: int = 5
    DEMO_RATE_LIMIT_RPD: int = 25
    DEMO_IP_RATE_LIMIT_RPM: int = 20
    DEMO_IP_RATE_LIMIT_RPD: int = 100
    DEMO_MAX_PROMPT_CHARS: int = 2_000
    DEMO_MAX_OUTPUT_TOKENS: int = 2048

    # Token billing (gateway usage = input + output tokens per /chat request)
    BILLING_ENABLED: bool = True
    FREE_SIGNUP_TOKENS: int = 10_000
    # Hard daily token spend cap per user — prevents runaway cost from scrapers.
    # 0 means unlimited (only the wallet balance applies).
    DAILY_TOKEN_BUDGET: int = 0
    # Comma-separated emails with unlimited gateway tokens (no deduct, no 402).
    # MUST be set explicitly via env — never hardcode emails here.
    BILLING_UNLIMITED_EMAILS: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_GROWTH: str = ""
    STRIPE_PRICE_SCALE: str = ""
    STRIPE_PRICE_ENTERPRISE: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_COMPATIBLE_API_KEY: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str = ""

    # Fernet key for optional at-rest encryption of full_prompt audit logs.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""

    DEFAULT_LLM_BACKEND: str = "anthropic"
    DEFAULT_MODEL: str = "claude-sonnet-4-20250514"

    # Comma-separated backends tried in order when the primary LLM backend
    # fails (generic gateway-level failover). Per-org policy fallbacks
    # (compliance_rules.llm_fallbacks) are tried before these.
    # Example: "openai,gemini,groq"
    LLM_FAILOVER_BACKENDS: str = ""

    # Global kill switch for the exact-hash response cache. The per-policy
    # output_rules.response_cache flag must ALSO be set for caching to apply.
    RESPONSE_CACHE_ENABLED: bool = False

    # Guardrail regex engine: "rust" (default — uses the compiled guardrail_core
    # PyO3 extension when importable) or "python" (pure-Python implementation,
    # no Rust toolchain needed). Falls back to Python automatically when the
    # extension is not installed.
    GUARDRAIL_ENGINE: str = "rust"

    # Open Policy Agent sidecar for org custom Rego rules (guardrails/opa.py).
    # http://opa:8181 is the `opa` service on the API's internal Docker
    # network; local dev: http://localhost:8181
    OPA_URL: str = "http://opa:8181"
    # Explicit per-query timeout. OPA failures fail CLOSED (the request is
    # blocked) — this value bounds how long a hung sidecar can hold a request.
    OPA_TIMEOUT_SECONDS: float = 2.0

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    @property
    def email_configured(self) -> bool:
        return bool(self.CLERK_SECRET_KEY) or bool(self.RESEND_API_KEY) or bool(self.SMTP_HOST and self.SMTP_FROM)

    @model_validator(mode="after")
    def normalize_database_url(self) -> "Settings":
        if not self.DATABASE_URL and self.POSTGRES_USER and self.POSTGRES_PASSWORD and self.POSTGRES_DB:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        if self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = "postgresql+asyncpg://" + self.DATABASE_URL[len("postgres://") :]
        elif self.DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in self.DATABASE_URL:
            self.DATABASE_URL = "postgresql+asyncpg://" + self.DATABASE_URL[len("postgresql://") :]

        if self.CLERK_SECRET_KEY:
            self.REQUIRE_EMAIL_VERIFICATION = False
        if not self.email_configured:
            self.REQUIRE_EMAIL_VERIFICATION = False

        if self.GROQ_API_KEY:
            self.GROQ_API_KEY = self.GROQ_API_KEY.strip()
        if self.OPENAI_API_KEY:
            self.OPENAI_API_KEY = self.OPENAI_API_KEY.strip()
        if self.ANTHROPIC_API_KEY:
            self.ANTHROPIC_API_KEY = self.ANTHROPIC_API_KEY.strip()
        if self.GEMINI_API_KEY:
            self.GEMINI_API_KEY = self.GEMINI_API_KEY.strip()
        if self.OPENAI_COMPATIBLE_API_KEY:
            self.OPENAI_COMPATIBLE_API_KEY = self.OPENAI_COMPATIBLE_API_KEY.strip()

        return self

    @model_validator(mode="after")
    def validate_production_config(self) -> "Settings":
        if self.APP_ENV != "production":
            return self

        normalized_secret = self.SECRET_KEY.lower()
        if (
            not self.SECRET_KEY
            or len(self.SECRET_KEY) < 32
            or "change" in normalized_secret
            or "dev-only" in normalized_secret
            or "replace" in normalized_secret
        ):
            raise ValueError("SECRET_KEY must be set to a strong production secret")

        if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg in production")
        if not self.RATE_LIMIT_REDIS_URL.startswith(("redis://", "rediss://")):
            raise ValueError("RATE_LIMIT_REDIS_URL must be configured in production")
        if self.DEFAULT_LLM_BACKEND == "groq" and not self.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY must be configured when DEFAULT_LLM_BACKEND=groq")
        if not self.PUBLIC_APP_URL.startswith("http"):
            raise ValueError("PUBLIC_APP_URL must be a full URL (used in verification and reset emails)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
