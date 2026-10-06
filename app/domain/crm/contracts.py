from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StageKind = Literal["open", "won", "lost"]
DEFAULT_STAGES: tuple[tuple[str, str, StageKind], ...] = (
    ("new", "Consulta nueva", "open"),
    ("need", "Necesidad identificada", "open"),
    ("offer", "Oferta presentada", "open"),
    ("decision", "En decisión", "open"),
    ("won", "Ganada", "won"),
    ("lost", "Perdida", "lost"),
)


class Stage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name: str = Field(min_length=1, max_length=100)
    kind: StageKind
    position: int = Field(ge=0)


class StageConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stages: list[Stage] = Field(min_length=3, max_length=30)
    expected_stages: list[Stage] | None = Field(
        default=None, min_length=3, max_length=30
    )

    @model_validator(mode="after")
    def complete(self) -> "StageConfiguration":
        if len({s.code for s in self.stages}) != len(self.stages):
            raise ValueError("duplicate stage code")
        if len({s.position for s in self.stages}) != len(self.stages):
            raise ValueError("duplicate stage position")
        if {s.kind for s in self.stages} != {"open", "won", "lost"}:
            raise ValueError("open, won and lost stages are required")
        return self


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=2000)
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("timezone required")
        return value


class OpportunityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    need: str | None = Field(default=None, max_length=4000)
    stage_code: str = Field(min_length=1, max_length=40)
    assigned_user_id: UUID
    next_action: ActionInput | None = None
    no_action_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    close_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def coherent(self) -> "OpportunityInput":
        if (self.amount is None) != (self.currency is None):
            raise ValueError("amount and currency must be provided together")
        if self.next_action and self.no_action_reason:
            raise ValueError("choose action or reason, not both")
        return self


class OpportunityCreate(OpportunityInput):
    contact_id: UUID
    conversation_id: UUID | None = None


class OpportunityUpdate(OpportunityInput):
    version: int = Field(ge=1)
    complete_previous_action: bool = False


class ActionRecord(BaseModel):
    id: UUID
    description: str
    due_at: datetime
    status: Literal["pending", "completed", "cancelled"]


class OpportunityRecord(BaseModel):
    id: UUID
    contact_id: UUID
    title: str
    need: str | None
    stage_code: str
    stage_kind: StageKind
    assigned_user_id: UUID
    next_action: ActionRecord | None
    no_action_reason: str | None
    close_reason: str | None
    amount: Decimal | None
    currency: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class OpportunityList(BaseModel):
    items: list[OpportunityRecord]
    total: int
    page: int
    page_size: int
    has_next: bool


FollowUpFilter = Literal["all", "overdue", "upcoming", "without_action"]


class FollowUpSummary(BaseModel):
    open: int
    overdue: int
    upcoming: int
    without_action: int


class FollowUpList(OpportunityList):
    as_of: datetime
    timezone: str
    summary: FollowUpSummary


class HistoryRecord(BaseModel):
    version: int
    actor_user_id: UUID
    occurred_at: datetime
    snapshot: OpportunityRecord


class CommercialContext(BaseModel):
    conversation_id: UUID
    contact_id: UUID | None
    channel_type: str
    channel_configuration_id: UUID | None
    account_name: str | None
    timezone: str
    can_write: bool


class CrmNotFound(ValueError):
    pass


class CrmConflict(ValueError):
    pass
