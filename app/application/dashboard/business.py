from datetime import datetime
from uuid import UUID

from app.application.business_calendar.compatibility import (
    BusinessHoursStateCompatibilityService,
)
from app.application.business_calendar.service import BusinessCalendarService
from app.domain.business_calendar.errors import BusinessCalendarError
from app.domain.dashboard.contracts import DashboardBusinessSummary


class DashboardBusinessStatusReader:
    def __init__(
        self,
        calendars: BusinessCalendarService,
        compatibility: BusinessHoursStateCompatibilityService,
    ) -> None:
        self.calendars = calendars
        self.compatibility = compatibility

    def status(
        self,
        organization_id: UUID,
        bot_id: UUID | None,
        evaluated_at: datetime,
    ) -> DashboardBusinessSummary:
        scope = "bot" if bot_id is not None else "organization"
        try:
            resolution = (
                self.calendars.resolve_applicable(organization_id, bot_id, evaluated_at)
                if bot_id is not None
                else self.calendars.resolve_default(organization_id, evaluated_at)
            )
        except BusinessCalendarError:
            return DashboardBusinessSummary(
                scope=scope, status="unknown", source="none"
            )
        if resolution is not None:
            return DashboardBusinessSummary(
                scope=scope,
                status=resolution.state,
                source="prd_015",
                next_change_at=resolution.next_change_at,
            )
        if bot_id is None:
            return DashboardBusinessSummary(
                scope=scope, status="unknown", source="none"
            )
        legacy = self.compatibility.state(organization_id, bot_id, evaluated_at)
        if legacy == "inside":
            return DashboardBusinessSummary(
                scope=scope, status="open", source="prd_005"
            )
        if legacy == "outside":
            return DashboardBusinessSummary(
                scope=scope, status="closed", source="prd_005"
            )
        return DashboardBusinessSummary(scope=scope, status="unknown", source="none")
