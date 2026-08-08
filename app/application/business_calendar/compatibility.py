from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.business_calendar.service import BusinessCalendarService
from app.domain.automation_management.contracts import BusinessHoursState
from app.domain.business_calendar.errors import BusinessCalendarError
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel


class BusinessHoursStateCompatibilityService:
    """Bridge PRD-012 to PRD-015 with an explicit PRD-005 fallback."""

    def __init__(
        self,
        calendars: BusinessCalendarService,
        session: Session,
    ) -> None:
        self.calendars = calendars
        self.session = session
        self.logger = structlog.get_logger(__name__)

    def state(
        self,
        organization_id: UUID,
        bot_id: UUID,
        occurred_at: datetime,
    ) -> BusinessHoursState:
        if occurred_at.tzinfo is None:
            return "unknown"
        try:
            resolution = self.calendars.resolve_applicable(
                organization_id,
                bot_id,
                occurred_at,
            )
        except BusinessCalendarError as exc:
            self.logger.warning(
                "business_hours_state_resolution_failed",
                organization_id=str(organization_id),
                bot_id=str(bot_id),
                safe_error_code=exc.safe_code,
            )
            return "unknown"
        if resolution is not None:
            return "inside" if resolution.state == "open" else "outside"
        return self._legacy_state(organization_id, bot_id, occurred_at)

    def _legacy_state(
        self,
        organization_id: UUID,
        bot_id: UUID,
        occurred_at: datetime,
    ) -> BusinessHoursState:
        config = self.session.scalar(
            select(BusinessConfigurationModel)
            .join(BotModel, BotModel.id == BusinessConfigurationModel.bot_id)
            .where(
                BotModel.organization_id == organization_id,
                BotModel.id == bot_id,
                BusinessConfigurationModel.bot_id == bot_id,
            )
        )
        if config is None:
            return "unknown"
        try:
            local = occurred_at.astimezone(ZoneInfo(config.timezone))
            day = (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )[local.weekday()]
            schedule = config.business_hours[day]
            if not isinstance(schedule, dict):
                return "unknown"
            enabled = schedule.get("enabled")
            open_time = schedule.get("open_time")
            close_time = schedule.get("close_time")
            if (
                not isinstance(enabled, bool)
                or not isinstance(open_time, str)
                or not isinstance(close_time, str)
            ):
                return "unknown"
            if not enabled:
                return "outside"
            current = local.strftime("%H:%M")
            return "inside" if open_time <= current < close_time else "outside"
        except (KeyError, TypeError, ValueError):
            return "unknown"
