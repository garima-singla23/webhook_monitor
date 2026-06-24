# config.py
# ─────────────────────────────────────────────
# All settings loaded from .env file
# NEVER hardcode secrets in code
# ─────────────────────────────────────────────

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase (database)
    supabase_url: str = ""
    supabase_key: str = ""

    # Redis (Upstash) — Phase 3
    upstash_redis_url: str = ""

    # Groq (free AI) — Phase 4
    groq_api_key: str = ""

    # Alerting (Slack + Email) — Phase 6
    slack_webhook_url: str = ""
    resend_api_key: str = ""
    alert_email_to: str = ""
    alert_email_from: str = "alerts@onboarding.resend.dev"

    # App settings
    app_name: str = "Webhook Monitor"
    environment: str = "development"
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# lru_cache means Settings() is only created once
# Not recreated on every function call
@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Use this throughout the app
settings = get_settings()