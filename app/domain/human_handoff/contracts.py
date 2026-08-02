from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

HandoffStatus = Literal["bot_active", "waiting_human", "human_active", "resolved"]


class HandoffRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason_code: str | None = Field(default=None, max_length=100)


class HandoffTransferRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assigned_user_id: UUID


class HandoffMessageRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str = Field(min_length=1, max_length=4096)
    idempotency_key: str = Field(min_length=8, max_length=128)


class HandoffSessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    conversation_id: UUID
    organization_id: UUID
    bot_id: UUID
    status: HandoffStatus
    assigned_user_id: UUID | None
    requested_at: datetime | None
    assigned_at: datetime | None
    resolved_at: datetime | None
    reason_code: str | None
    last_activity_at: datetime
    version: int


class HandoffListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[HandoffSessionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
