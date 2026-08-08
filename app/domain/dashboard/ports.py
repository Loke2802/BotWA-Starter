from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.dashboard.contracts import (
    DashboardAutomationSummary,
    DashboardBotSummary,
    DashboardBusinessSummary,
    DashboardContactSummary,
    DashboardConversationSummary,
    DashboardHandoffSummary,
    DashboardIntegrationSummary,
)


@dataclass(frozen=True)
class DashboardScope:
    organization_id: UUID
    bot_id: UUID | None
    timezone: str


@dataclass(frozen=True)
class DashboardHandoffAggregate:
    summary: DashboardHandoffSummary
    oldest_active_since: datetime | None


@dataclass(frozen=True)
class DashboardAggregate:
    bots: DashboardBotSummary
    conversations: DashboardConversationSummary
    handoffs: DashboardHandoffAggregate
    automations: DashboardAutomationSummary
    integrations: DashboardIntegrationSummary
    contacts: DashboardContactSummary


class DashboardRepository(Protocol):
    def scope(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> DashboardScope | None: ...

    def aggregate(
        self,
        scope: DashboardScope,
        period_start: datetime,
        period_end: datetime,
    ) -> DashboardAggregate: ...


class DashboardBusinessReader(Protocol):
    def status(
        self,
        organization_id: UUID,
        bot_id: UUID | None,
        evaluated_at: datetime,
    ) -> DashboardBusinessSummary: ...
