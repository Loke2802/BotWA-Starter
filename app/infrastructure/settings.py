from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BOTWA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BotWA Starter"
    environment: str = "local"
    log_level: str = "INFO"
    api_version: str = "v1"
    database_url: str = Field(
        default="postgresql+psycopg://botwa:botwa@localhost:5432/botwa"
    )
    use_database: bool = False
    whatsapp_webhook_verify_token: str = "botwa_verify_token"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v22.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
