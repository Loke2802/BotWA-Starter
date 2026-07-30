from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WhatsAppChannelConfigurationStatus = Literal["draft", "active", "inactive"]


def _required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    return cleaned


def _optional_secret(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


class WhatsAppChannelConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    bot_id: UUID
    display_name: str
    phone_number_id: str
    whatsapp_business_account_id: str
    public_webhook_id: UUID
    status: WhatsAppChannelConfigurationStatus
    webhook_enabled: bool
    verify_token_configured: bool
    access_token_configured: bool
    app_secret_configured: bool
    created_by_user_id: UUID
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class WhatsAppChannelConfigurationCreate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    phone_number_id: str = Field(min_length=1, max_length=100)
    whatsapp_business_account_id: str = Field(min_length=1, max_length=100)
    webhook_enabled: bool = True
    verify_token: str | None = Field(default=None, max_length=500)
    access_token: str | None = Field(default=None, max_length=4000)
    app_secret: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "display_name",
        "phone_number_id",
        "whatsapp_business_account_id",
    )
    @classmethod
    def validate_required_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _required_text(value, str(field_name))

    @field_validator("verify_token", "access_token", "app_secret")
    @classmethod
    def validate_optional_secret(cls, value: str | None, info: object) -> str | None:
        field_name = getattr(info, "field_name", "secret")
        return _optional_secret(value, str(field_name))


class WhatsAppChannelConfigurationUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone_number_id: str | None = Field(default=None, min_length=1, max_length=100)
    whatsapp_business_account_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    webhook_enabled: bool | None = None

    @field_validator(
        "display_name",
        "phone_number_id",
        "whatsapp_business_account_id",
    )
    @classmethod
    def validate_optional_text(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        field_name = getattr(info, "field_name", "value")
        return _required_text(value, str(field_name))


class WhatsAppSecretRotation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verify_token: str | None = Field(default=None, max_length=500)
    access_token: str | None = Field(default=None, max_length=4000)
    app_secret: str | None = Field(default=None, max_length=1000)

    @field_validator("verify_token", "access_token", "app_secret")
    @classmethod
    def validate_optional_secret(cls, value: str | None, info: object) -> str | None:
        field_name = getattr(info, "field_name", "secret")
        return _optional_secret(value, str(field_name))

    @model_validator(mode="after")
    def require_at_least_one_secret(self) -> Self:
        if (
            self.verify_token is None
            and self.access_token is None
            and self.app_secret is None
        ):
            raise ValueError("at least one secret is required")
        return self


class WhatsAppChannelConfigurationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    configuration: WhatsAppChannelConfiguration


class WhatsAppChannelConfigurationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[WhatsAppChannelConfiguration]
    total: int
    page: int
    page_size: int
