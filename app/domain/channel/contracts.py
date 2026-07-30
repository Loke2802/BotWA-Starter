from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChannelType = Literal["whatsapp"]


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
