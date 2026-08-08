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
    use_database: bool = True
    whatsapp_webhook_verify_token: str = "botwa_verify_token"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v22.0"
    whatsapp_secret_encryption_key: str = ""
    whatsapp_secret_previous_encryption_keys: str = ""
    integration_secret_encryption_key: str = ""
    integration_secret_previous_encryption_keys: str = ""
    integration_oauth_state_secret: str = ""
    integration_oauth_state_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""
    google_calendar_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    contact_identity_hmac_key: str = ""
    whatsapp_live_client_mode: str = "disabled"
    whatsapp_webhook_max_body_bytes: int = Field(
        default=1_048_576,
        ge=1_024,
        le=10_485_760,
    )
    whatsapp_webhook_max_events: int = Field(default=100, ge=1, le=1_000)
    whatsapp_outbound_max_text_chars: int = Field(
        default=4_096,
        ge=1,
        le=65_536,
    )
    whatsapp_outbound_max_attempts: int = Field(default=3, ge=1, le=10)
    whatsapp_outbound_retry_base_seconds: float = Field(
        default=1.0,
        ge=0,
        le=300,
    )
    whatsapp_outbound_retry_max_seconds: float = Field(
        default=60.0,
        ge=0,
        le=3_600,
    )
    whatsapp_meta_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    auth_secret_key: str = "local-development-secret-change-me"
    auth_algorithm: str = "HS256"
    auth_access_token_expire_minutes: int = 30
    auth_password_min_length: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
