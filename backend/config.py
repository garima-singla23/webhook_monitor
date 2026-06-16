from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase (database)
    supabase_url: str = ""
    supabase_key: str = ""

    # App settings
    app_name: str = "Webhook Monitor"
    environment: str = "development"
    debug: bool = True

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

print("URL =", settings.supabase_url)
print("KEY =", settings.supabase_key[:10] if settings.supabase_key else "EMPTY")