from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DashboardPeriodPreset = Literal["today", "last_7_days", "last_30_days"]
DashboardMetricScope = Literal["organization", "bot"]
DashboardBusinessState = Literal["open", "closed", "unknown"]
DashboardBusinessSource = Literal["prd_015", "prd_005", "none"]


class DashboardPeriodResponse(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    preset: DashboardPeriodPreset | Literal["custom"]
    from_: datetime = Field(alias="from")
    to: datetime
    timezone: str


class DashboardBusinessSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: DashboardMetricScope
    status: DashboardBusinessState
    source: DashboardBusinessSource
    next_change_at: datetime | None = None


class DashboardBotSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: DashboardMetricScope
    total: int = Field(ge=0)
    active: int = Field(ge=0)
    inactive: int = Field(ge=0)


class DashboardConversationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: DashboardMetricScope
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    closed: int = Field(ge=0)
    archived: int = Field(ge=0)
    started_in_period: int = Field(ge=0)


class DashboardHandoffSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: DashboardMetricScope
    active: int = Field(ge=0)
    pending: int = Field(ge=0)
    created_in_period: int = Field(ge=0)
    completed_in_period: int = Field(ge=0)
    oldest_active_age_seconds: int | None = Field(default=None, ge=0)


class DashboardAutomationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: DashboardMetricScope
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    running: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    cancelled: int = Field(ge=0)


class DashboardIntegrationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: DashboardMetricScope
    total: int = Field(ge=0)
    active: int = Field(ge=0)
    healthy: int = Field(ge=0)
    degraded: int = Field(ge=0)
    unreachable: int = Field(ge=0)
    auth_error: int = Field(ge=0)
    unknown: int = Field(ge=0)


class DashboardContactSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: Literal["organization"] = "organization"
    total: int = Field(ge=0)
    created_in_period: int = Field(ge=0)


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: UUID
    bot_id: UUID | None
    period: DashboardPeriodResponse
    generated_at: datetime
    business: DashboardBusinessSummary
    bots: DashboardBotSummary
    conversations: DashboardConversationSummary
    handoffs: DashboardHandoffSummary
    automations: DashboardAutomationSummary
    integrations: DashboardIntegrationSummary
    contacts: DashboardContactSummary
