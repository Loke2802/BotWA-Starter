from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BOTWA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BotWA Starter"
    environment: Environment = Environment.DEVELOPMENT
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
    auth_algorithm: Literal["HS256"] = "HS256"
    auth_access_token_expire_minutes: int = 30
    auth_password_min_length: int = 12
    auth_password_max_length: int = Field(default=256, ge=64, le=4_096)
    public_bootstrap_enabled: bool = True
    legacy_core_api_enabled: bool = True
    legacy_whatsapp_enabled: bool = True
    global_max_body_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    allowed_hosts: Annotated[tuple[str, ...], NoDecode] = (
        "localhost",
        "127.0.0.1",
        "testserver",
    )
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()
    cors_allow_credentials: bool = False
    trusted_proxy_hosts: Annotated[tuple[str, ...], NoDecode] = ()
    openapi_enabled: bool | None = None
    https_enabled: bool = False
    rate_limit_hmac_key: str = ""
    audit_cursor_signing_key: str = ""
    auth_login_rate_limit_attempts: int = Field(default=10, ge=1, le=1_000)
    auth_login_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    public_bootstrap_rate_limit_attempts: int = Field(default=5, ge=1, le=1_000)
    public_bootstrap_rate_limit_window_seconds: int = Field(
        default=300, ge=1, le=86_400
    )
    webhook_rate_limit_attempts: int = Field(default=300, ge=1, le=100_000)
    webhook_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    billing_enabled: bool = False
    billing_provider: str = "mercado_pago"
    billing_mercado_pago_access_token: str = ""
    billing_mercado_pago_webhook_secret: str = ""
    billing_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    billing_read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    billing_success_url: str = ""
    billing_cancel_url: str = ""
    billing_webhook_max_body_bytes: int = Field(default=262_144, ge=1_024, le=1_048_576)
    billing_webhook_signature_tolerance_seconds: int = Field(
        default=300, ge=30, le=3_600
    )
    billing_fallback_plan_code: str = ""
    billing_freshness_seconds: int = Field(default=900, ge=60, le=86_400)
    billing_due_batch_size: int = Field(default=100, ge=1, le=1_000)
    billing_provider_change_lead_seconds: int = Field(default=3_600, ge=300, le=86_400)

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        return Environment.DEVELOPMENT if value == "local" else value

    @field_validator(
        "allowed_hosts", "cors_origins", "trusted_proxy_hosts", mode="before"
    )
    @classmethod
    def parse_csv_tuple(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @property
    def effective_openapi_enabled(self) -> bool:
        if self.openapi_enabled is not None:
            return self.openapi_enabled
        return self.environment != Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
