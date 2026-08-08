from datetime import UTC, datetime, time, timedelta
from time import perf_counter
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from app.application.dashboard.metrics import DashboardMetrics
from app.domain.dashboard.contracts import (
    DashboardPeriodPreset,
    DashboardPeriodResponse,
    DashboardSummaryResponse,
)
from app.domain.dashboard.errors import (
    DashboardForbidden,
    DashboardInvalidFilter,
    DashboardInvalidRange,
    DashboardNotFound,
    DashboardRangeTooLarge,
)
from app.domain.dashboard.ports import DashboardBusinessReader, DashboardRepository
from app.domain.user.contracts import User
from app.security.authorization import AuthorizationError, require_scoped_permission


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class DashboardQueryService:
    def __init__(
        self,
        repository: DashboardRepository,
        business: DashboardBusinessReader,
        *,
        metrics: DashboardMetrics | None = None,
    ) -> None:
        self.repository = repository
        self.business = business
        self.metrics = metrics or DashboardMetrics()
        self.logger = structlog.get_logger(__name__)

    def summary(
        self,
        organization_id: UUID,
        actor: User,
        *,
        bot_id: UUID | None = None,
        period: DashboardPeriodPreset | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        generated_at: datetime | None = None,
    ) -> DashboardSummaryResponse:
        started = perf_counter()
        endpoint = "summary"
        try:
            try:
                require_scoped_permission(actor, "dashboard.read", organization_id)
            except AuthorizationError as exc:
                raise DashboardForbidden("permission denied") from exc
            scope = self.repository.scope(organization_id, bot_id)
            if scope is None:
                raise DashboardNotFound("dashboard scope not found")
            now = (generated_at or datetime.now(UTC)).astimezone(UTC)
            selected_period = self._period(
                scope.timezone,
                now,
                period=period,
                from_=from_,
                to=to,
            )
            aggregate = self.repository.aggregate(
                scope, selected_period.from_, selected_period.to
            )
            oldest_active_age: int | None = None
            if aggregate.handoffs.oldest_active_since is not None:
                oldest_active_age = max(
                    0,
                    int(
                        (
                            now - _aware(aggregate.handoffs.oldest_active_since)
                        ).total_seconds()
                    ),
                )
            handoffs = aggregate.handoffs.summary.model_copy(
                update={"oldest_active_age_seconds": oldest_active_age}
            )
            response = DashboardSummaryResponse(
                organization_id=organization_id,
                bot_id=bot_id,
                period=selected_period,
                generated_at=now,
                business=self.business.status(organization_id, bot_id, now),
                bots=aggregate.bots,
                conversations=aggregate.conversations,
                handoffs=handoffs,
                automations=aggregate.automations,
                integrations=aggregate.integrations,
                contacts=aggregate.contacts,
            )
        except Exception as exc:
            result = getattr(exc, "safe_code", "DASHBOARD_UNAVAILABLE")
            self.metrics.record_error(endpoint, str(result))
            self.metrics.record_request(
                endpoint, str(result), int((perf_counter() - started) * 1000)
            )
            self.logger.warning(
                "dashboard_query_failed", endpoint=endpoint, result=str(result)
            )
            raise
        self.metrics.record_request(
            endpoint, "success", int((perf_counter() - started) * 1000)
        )
        self.logger.info(
            "dashboard_query_completed", endpoint=endpoint, result="success"
        )
        return response

    @staticmethod
    def _period(
        timezone_name: str,
        generated_at: datetime,
        *,
        period: DashboardPeriodPreset | None,
        from_: datetime | None,
        to: datetime | None,
    ) -> DashboardPeriodResponse:
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise DashboardInvalidFilter("dashboard timezone is invalid") from exc
        if from_ is not None or to is not None:
            if period is not None:
                raise DashboardInvalidFilter(
                    "period cannot be combined with an explicit range"
                )
            if from_ is None or to is None:
                raise DashboardInvalidRange("from and to are both required")
            if from_.tzinfo is None or to.tzinfo is None or from_ >= to:
                raise DashboardInvalidRange("dashboard range must be ordered and aware")
            start, end = from_.astimezone(UTC), to.astimezone(UTC)
            if end - start > timedelta(days=90):
                raise DashboardRangeTooLarge("dashboard range exceeds 90 days")
            return DashboardPeriodResponse(
                preset="custom", from_=start, to=end, timezone=timezone_name
            )
        preset = period or "today"
        local_today = generated_at.astimezone(zone).date()
        days = {"today": 1, "last_7_days": 7, "last_30_days": 30}[preset]
        local_start = local_today - timedelta(days=days - 1)
        local_end = local_today + timedelta(days=1)
        start = datetime.combine(local_start, time.min, zone).astimezone(UTC)
        end = datetime.combine(local_end, time.min, zone).astimezone(UTC)
        return DashboardPeriodResponse(
            preset=preset, from_=start, to=end, timezone=timezone_name
        )
