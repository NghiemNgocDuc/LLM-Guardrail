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
    DEMO_MAX_OUTPUT_TOKENS: int = 256

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_COMPATIBLE_API_KEY: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str = ""

    DEFAULT_LLM_BACKEND: str = "anthropic"
    DEFAULT_MODEL: str = "claude-sonnet-4-20250514"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
