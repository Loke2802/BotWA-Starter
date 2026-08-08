from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AnalyticsGroupBy = Literal["day", "week", "month"]
AnalyticsCompare = Literal["previous_period"]


class AnalyticsCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversations_started: int = Field(ge=0)
    conversations_closed: int = Field(ge=0)
    handoffs_created: int = Field(ge=0)
    handoffs_resolved: int = Field(ge=0)
    handoff_resolution_seconds_sum: int = Field(ge=0)
    handoff_resolution_count: int = Field(ge=0)
    automation_executions_created: int = Field(ge=0)
    automation_succeeded: int = Field(ge=0)
    automation_failed: int = Field(ge=0)
    automation_skipped: int = Field(ge=0)
    automation_cancelled: int = Field(ge=0)
    contacts_created: int = Field(ge=0)


class AnalyticsMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversations_started: int = Field(ge=0)
    conversations_closed: int = Field(ge=0)
    handoffs_created: int = Field(ge=0)
    handoffs_resolved: int = Field(ge=0)
    handoff_average_resolution_seconds: float | None
    automation_executions_created: int = Field(ge=0)
    automation_succeeded: int = Field(ge=0)
    automation_failed: int = Field(ge=0)
    automation_skipped: int = Field(ge=0)
    automation_cancelled: int = Field(ge=0)
    automation_success_rate: float | None
    contacts_created: int = Field(ge=0)


class AnalyticsSeriesPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    period_start: date
    period_end: date
    metrics: AnalyticsMetrics


class AnalyticsMetricChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    absolute_change: float
    percent_change: float | None


class AnalyticsComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    current: AnalyticsMetrics
    previous: AnalyticsMetrics
    change: dict[str, AnalyticsMetricChange]


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    organization_id: UUID
    bot_id: UUID | None
    reporting_timezone: str
    from_: date = Field(alias="from", serialization_alias="from")
    to: date
    group_by: AnalyticsGroupBy
    contacts_scope: Literal["organization"] = "organization"
    complete: bool
    source_watermark_at: datetime | None
    series: list[AnalyticsSeriesPoint]
    summary: AnalyticsMetrics
    comparison: AnalyticsComparison | None = None


class AnalyticsRebuildResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: UUID
    bot_id: UUID | None
    local_date: date
    reporting_timezone: str
    source_watermark_at: datetime
    computed_at: datetime
