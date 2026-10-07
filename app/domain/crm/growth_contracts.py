from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DuplicateCandidate(BaseModel):
    source_id: UUID
    target_id: UUID
    source_name: str
    target_name: str
    reasons: list[str]


class DuplicateList(BaseModel):
    items: list[DuplicateCandidate]
    page: int
    has_next: bool
    scanned: int
    scan_limited: bool
    total: int = 0


class MergeContact(BaseModel):
    id: UUID
    name: str
    channel: str
    identifier: str
    notes: str | None
    profile: dict[str, str | int | None]
    opportunities: int
    conversations: int
    activities: int


class MergePreview(BaseModel):
    source: MergeContact
    target: MergeContact
    token: str
    explanation: str


class MergeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    target_id: UUID
    review_token: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]+$")


class MergeResult(BaseModel):
    source_id: UUID
    target_id: UUID
    replayed: bool


class ClosingMetric(BaseModel):
    assigned_user_id: UUID
    won: int
    lost: int
    conversion_percent: Decimal | None
    currency: str | None
    won_amount: Decimal | None


class StageDuration(BaseModel):
    stage_code: str
    opportunity_count: int
    total_hours: Decimal
    average_hours: Decimal


class SalesMetrics(BaseModel):
    date_from: datetime | None
    date_to: datetime
    as_of: datetime
    timezone: str
    can_read_amounts: bool
    closings: list[ClosingMetric]
    durations: list[StageDuration]
    explanation: str
