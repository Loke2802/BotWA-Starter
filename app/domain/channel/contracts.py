from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChannelType = Literal["whatsapp"]
ChannelMetadataValue = str | int | float | bool | None


def _external_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("external_channel_id cannot be empty")
    return cleaned


class ChannelIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_type: ChannelType
    external_channel_id: str = Field(min_length=1, max_length=255)

    @field_validator("external_channel_id")
    @classmethod
    def validate_external_channel_id(cls, value: str) -> str:
        return _external_id(value)


class ResolvedChannelContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_type: ChannelType
    organization_id: UUID
    bot_id: UUID
    channel_configuration_id: UUID
    external_channel_id: str = Field(min_length=1, max_length=255)

    @field_validator("external_channel_id")
    @classmethod
    def validate_external_channel_id(cls, value: str) -> str:
        return _external_id(value)


class InboundChannelMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    channel_type: ChannelType
    external_message_id: str = Field(min_length=1, max_length=255)
    external_sender_id: str = Field(min_length=1, max_length=255)
    external_recipient_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=65_536)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_context: ResolvedChannelContext
    metadata: dict[str, ChannelMetadataValue] = Field(default_factory=dict)

    @field_validator(
        "external_message_id",
        "external_sender_id",
        "external_recipient_id",
    )
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("external identifier cannot be empty")
        return cleaned

    @field_validator("metadata")
    @classmethod
    def validate_metadata(
        cls,
        value: dict[str, ChannelMetadataValue],
    ) -> dict[str, ChannelMetadataValue]:
        if len(value) > 20:
            raise ValueError("channel metadata cannot contain more than 20 fields")
        return value


class OutboundChannelMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    channel_type: ChannelType
    external_recipient_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=65_536)
    reply_to_external_message_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    metadata: dict[str, ChannelMetadataValue] = Field(default_factory=dict)

    @field_validator("external_recipient_id")
    @classmethod
    def validate_recipient_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("external_recipient_id cannot be empty")
        return cleaned


class ChannelDeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_message_id: str = Field(min_length=1, max_length=255)
    status: Literal["sent"] = "sent"


class MessageProcessingResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["processed", "duplicate", "ignored", "failed"]
    receipt_id: UUID | None = None
    outbound_attempt_ids: tuple[UUID, ...] = ()
    error_code: str | None = Field(default=None, max_length=100)
