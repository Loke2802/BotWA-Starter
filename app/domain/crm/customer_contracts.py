"""Customer workspace, recorded activities and read-only commercial metrics."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.crm.contracts import OpportunityList, Stage


class ActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["call", "meeting", "note"]
    description: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime
    opportunity_id: UUID | None = None

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timezone required")
        return value


class CustomerActivity(BaseModel):
    id: UUID
    contact_id: UUID
    opportunity_id: UUID | None
    kind: str
    description: str
    occurred_at: datetime
    created_at: datetime
    actor_user_id: UUID


class ActivityList(BaseModel):
    items: list[CustomerActivity]
    total: int
    page: int
    has_next: bool


class CustomerConversation(BaseModel):
    id: UUID
    status: str
    created_at: datetime


class CustomerWorkspace(BaseModel):
    contact_id: UUID
    timezone: str
    can_write: bool
    can_read_conversations: bool
    opportunities: OpportunityList
    conversations: list[CustomerConversation]
    conversation_total: int
    conversation_page: int
    conversations_has_next: bool
    stages: list[Stage]


class CommercialMetric(BaseModel):
    assigned_user_id: UUID
    kind: Literal["open", "won", "lost"]
    count: int
    currency: str | None
    amount: Decimal | None


class CommercialReport(BaseModel):
    date_from: datetime | None
    date_to: datetime | None
    timezone: str
    can_read_amounts: bool
    items: list[CommercialMetric]


class CommercialSuggestion(BaseModel):
    available: bool
    explanation: str
    conversation_id: UUID
    memory_revision: int | None = None
    need: str | None = None
    stage_code: str | None = None
    next_action: str | None = None
    evidence: list[str] = Field(default_factory=list)


class CustomerAction(BaseModel):
    id: UUID
    opportunity_id: UUID
    description: str
    due_at: datetime
    status: Literal["pending", "completed", "cancelled"]
    resolved_at: datetime | None
    assigned_user_id: UUID


class CustomerActionList(BaseModel):
    items: list[CustomerAction]
    total: int
    page: int
    has_next: bool
