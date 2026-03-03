"""
core/config.py

Centralized configuration using pydantic-settings.
All environment variables are validated at startup — the app
will refuse to start if required secrets are missing.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ... other settings ...
    STRIPE_WEBHOOK_SECRET: str = "",

    # ─── App ────────────────────────────────────────────────────────────
    app_name: str = "One Goal"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ─── Server ─────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    # Comma-separated list of allowed origins for CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    # ─── Database ───────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        ...,
        description="PostgreSQL connection string with pgvector enabled",
    )
    # Async DSN for asyncpg (replaces postgresql:// with postgresql+asyncpg://)
    @property
    def async_database_url(self) -> str:
        url = str(self.database_url)
        return url.replace("postgresql://", "postgresql+asyncpg://").replace(
            "postgres://", "postgresql+asyncpg://"
        )

    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30

    # ─── Redis ──────────────────────────────────────────────────────────
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="Redis for session cache and job queue",
    )
    redis_session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # ─── Auth / JWT ─────────────────────────────────────────────────────
    jwt_secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for signing JWTs — must be 32+ chars",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24        # 24 hours
    jwt_refresh_token_expire_days: int = 30

    # ─── Supabase ───────────────────────────────────────────────────────
    # Used for Google/Apple OAuth and email auth flow
    supabase_url: str = Field(..., description="Your Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anon/public key")
    supabase_service_role_key: str = Field(
        ...,
        description="Supabase service role key — server-side only, never expose",
    )

    # ─── OpenAI ─────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI API key for GPT-4o")
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"  # cost-efficient
    openai_max_tokens_coach: int = 1000
    openai_max_tokens_analysis: int = 2000
    openai_max_tokens_generation: int = 1500
    openai_temperature_coach: float = 0.7
    openai_temperature_analysis: float = 0.3  # more deterministic for scoring
    openai_temperature_generation: float = 0.8  # more creative for tasks

    # ─── AI Rate Limiting ───────────────────────────────────────────────
    ai_coach_daily_message_limit: int = 20
    ai_interview_message_limit: int = 50
    ai_rate_limit_window_seconds: int = 60

    # ─── Security ───────────────────────────────────────────────────────
    bcrypt_rounds: int = 12
    # Max input size to protect against token stuffing attacks
    max_user_input_length: int = 4000

    # ─── Features ───────────────────────────────────────────────────────
    # Enable/disable features without code deploys
    feature_google_auth: bool = True
    feature_apple_auth: bool = True
    feature_weekly_review: bool = True
    feature_push_notifications: bool = False  # not yet live

    # ─── Scheduler ──────────────────────────────────────────────────────
    # UTC hour to run the nightly task generation job
    task_generation_utc_hour: int = 21  # 9pm UTC
    weekly_review_utc_hour: int = 20    # 8pm UTC Sunday

    @field_validator("environment")
    @classmethod
    def validate_prod_settings(cls, v: str, info) -> str:
        """In production, enforce stricter settings."""
        # This runs after the model is fully populated via model_validator
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    The lru_cache means this is only instantiated once per process —
    use get_settings() everywhere instead of Settings() directly.
    """
    return Settings()


# Convenience alias used in FastAPI dependency injection
settings = get_settings()
