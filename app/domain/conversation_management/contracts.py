from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ConversationStatus = Literal["open", "closed", "archived"]
ConversationDirection = Literal["inbound", "outbound"]
ConversationMessageStatus = Literal[
    "received",
    "processed",
    "pending",
    "sent",
    "delivered",
    "read",
    "failed",
]


class ConversationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    organization_id: UUID
    bot_id: UUID
    channel_type: str
    status: ConversationStatus
    masked_customer_identifier: str
    started_at: datetime
    last_message_at: datetime | None = None
    message_count: int = Field(ge=0)
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    channel_configuration_id: UUID | None = None
    external_conversation_metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
    inbound_message_count: int = Field(ge=0)
    outbound_message_count: int = Field(ge=0)
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None
    closed_at: datetime | None = None


class ConversationMessageRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    conversation_id: UUID
    direction: ConversationDirection
    channel_type: str
    message_type: str
    text: str | None = None
    status: ConversationMessageStatus
    occurred_at: datetime
    provider_message_id: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


class ConversationMessageListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ConversationMessageRecord]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


def utc_now() -> datetime:
    return datetime.now(UTC)
