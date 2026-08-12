from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from time import perf_counter
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

from app.application.analytics.metrics import AnalyticsMetricsRegistry
from app.application.plans.service import PlanEnforcementService
from app.domain.analytics.contracts import (
    AnalyticsCompare,
    AnalyticsComparison,
    AnalyticsCounts,
    AnalyticsGroupBy,
    AnalyticsMetricChange,
    AnalyticsMetrics,
    AnalyticsRebuildResult,
    AnalyticsResponse,
    AnalyticsSeriesPoint,
)
from app.domain.analytics.errors import (
    AnalyticsDataIncomplete,
    AnalyticsForbidden,
    AnalyticsInvalidRange,
    AnalyticsNotFound,
    AnalyticsRangeTooLarge,
)
from app.domain.analytics.ports import (
    AnalyticsDailyValue,
    AnalyticsRepository,
    AnalyticsScope,
)
from app.domain.user.contracts import User
from app.security.authorization import AuthorizationError, require_scoped_permission

_COUNT_FIELDS = (
    "conversations_started",
    "conversations_closed",
    "handoffs_created",
    "handoffs_resolved",
    "handoff_resolution_seconds_sum",
    "handoff_resolution_count",
    "automation_executions_created",
    "automation_succeeded",
    "automation_failed",
    "automation_skipped",
    "automation_cancelled",
    "contacts_created",
)


def _empty_counts() -> dict[str, int]:
    return {field: 0 for field in _COUNT_FIELDS}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _add(target: dict[str, int], source: AnalyticsCounts, *, contacts: bool) -> None:
    values = source.model_dump()
    for field in _COUNT_FIELDS:
        if (field == "contacts_created") == contacts:
            target[field] += int(values[field])


def _metrics(counts: dict[str, int]) -> AnalyticsMetrics:
    resolution_count = counts["handoff_resolution_count"]
    resolved_average = (
        counts["handoff_resolution_seconds_sum"] / resolution_count
        if resolution_count
        else None
    )
    success_denominator = counts["automation_succeeded"] + counts["automation_failed"]
    success_rate = (
        counts["automation_succeeded"] / success_denominator
        if success_denominator
        else None
    )
    return AnalyticsMetrics(
        conversations_started=counts["conversations_started"],
        conversations_closed=counts["conversations_closed"],
        handoffs_created=counts["handoffs_created"],
        handoffs_resolved=counts["handoffs_resolved"],
        handoff_average_resolution_seconds=resolved_average,
        automation_executions_created=counts["automation_executions_created"],
        automation_succeeded=counts["automation_succeeded"],
        automation_failed=counts["automation_failed"],
        automation_skipped=counts["automation_skipped"],
        automation_cancelled=counts["automation_cancelled"],
        automation_success_rate=success_rate,
        contacts_created=counts["contacts_created"],
    )


class AnalyticsProjectionService:
    def __init__(
        self,
        repository: AnalyticsRepository,
        *,
        metrics: AnalyticsMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.metrics = metrics or AnalyticsMetricsRegistry()
        self.logger = structlog.get_logger(__name__)

    def rebuild_day(
        self, organization_id: UUID, bot_id: UUID | None, local_date: date
    ) -> AnalyticsRebuildResult:
        started = perf_counter()
        try:
            scope = self.repository.scope(organization_id, bot_id)
            if scope is None:
                raise AnalyticsNotFound("analytics scope not found")
            day_start, day_end = self._bucket(scope.timezone, local_date)
            watermark = datetime.now(UTC)
            if bot_id is not None and not self._bot_expected(scope, bot_id, day_end):
                computed_at = datetime.now(UTC)
                self.repository.commit()
                self._record(
                    "analytics_projection_rebuild_total",
                    "rebuild_day",
                    "structural_skip",
                    started,
                )
                return AnalyticsRebuildResult(
                    organization_id=organization_id,
                    bot_id=bot_id,
                    local_date=local_date,
                    reporting_timezone=scope.timezone,
                    source_watermark_at=watermark,
                    computed_at=computed_at,
                    written=False,
                )
            counts = self.repository.aggregate_sources(
                scope, local_date, day_start, day_end, watermark
            )
            computed_at = datetime.now(UTC)
            self.repository.upsert_day(
                scope, local_date, counts, watermark, computed_at
            )
            self.repository.commit()
        except Exception as exc:
            self.repository.rollback()
            result = getattr(exc, "safe_code", "ANALYTICS_UNAVAILABLE")
            self._record(
                "analytics_projection_errors_total", "rebuild_day", str(result), started
            )
            self.logger.warning(
                "analytics_projection_failed",
                operation="rebuild_day",
                result=str(result),
            )
            raise
        self._record(
            "analytics_projection_rebuild_total", "rebuild_day", "success", started
        )
        return AnalyticsRebuildResult(
            organization_id=organization_id,
            bot_id=bot_id,
            local_date=local_date,
            reporting_timezone=scope.timezone,
            source_watermark_at=watermark,
            computed_at=computed_at,
            written=True,
        )

    def rebuild_range(
        self,
        organization_id: UUID,
        bot_id: UUID | None,
        from_local_date: date,
        to_local_date: date,
    ) -> list[AnalyticsRebuildResult]:
        days = self._range_days(from_local_date, to_local_date)
        return [
            self.rebuild_day(
                organization_id, bot_id, from_local_date + timedelta(days=offset)
            )
            for offset in range(days)
        ]

    @staticmethod
    def _bucket(timezone_name: str, local_date: date) -> tuple[datetime, datetime]:
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise AnalyticsInvalidRange("reporting timezone is invalid") from exc
        start = datetime.combine(local_date, time.min, zone).astimezone(UTC)
        end = datetime.combine(
            local_date + timedelta(days=1), time.min, zone
        ).astimezone(UTC)
        return start, end

    @staticmethod
    def _range_days(from_: date, to: date) -> int:
        days = (to - from_).days
        if days <= 0:
            raise AnalyticsInvalidRange("analytics range must be ordered")
        if days > 366:
            raise AnalyticsRangeTooLarge("analytics range exceeds 366 days")
        return days

    @staticmethod
    def _bot_expected(
        scope: AnalyticsScope, bot_id: UUID, bucket_end_utc: datetime
    ) -> bool:
        return any(
            bot.bot_id == bot_id and _aware_utc(bot.created_at) < bucket_end_utc
            for bot in scope.bots
        )

    def _record(self, metric: str, operation: str, result: str, started: float) -> None:
        self.metrics.record(
            metric, operation, result, int((perf_counter() - started) * 1000)
        )


class AnalyticsQueryService:
    def __init__(
        self,
        repository: AnalyticsRepository,
        *,
        metrics: AnalyticsMetricsRegistry | None = None,
        plan_enforcement: PlanEnforcementService | None = None,
    ) -> None:
        self.repository = repository
        self.metrics = metrics or AnalyticsMetricsRegistry()
        self.logger = structlog.get_logger(__name__)
        self.plan_enforcement = plan_enforcement

    def query(
        self,
        organization_id: UUID,
        actor: User,
        *,
        bot_id: UUID | None,
        from_: date,
        to: date,
        group_by: AnalyticsGroupBy,
        compare: AnalyticsCompare | None,
    ) -> AnalyticsResponse:
        started = perf_counter()
        try:
            try:
                require_scoped_permission(actor, "analytics.read", organization_id)
            except AuthorizationError as exc:
                raise AnalyticsForbidden("permission denied") from exc
            if self.plan_enforcement is not None:
                self.plan_enforcement.require_feature(organization_id, "analytics")
            days = AnalyticsProjectionService._range_days(from_, to)
            scope = self.repository.scope(organization_id, bot_id)
            if scope is None:
                raise AnalyticsNotFound("analytics scope not found")
            current_rows = self.repository.daily_values(scope, from_, to)
            complete = self._complete(scope, current_rows, from_, to)
            current_counts = self._daily_counts(scope, current_rows)
            series = self._series(current_counts, from_, to, group_by)
            summary_counts = self._sum_counts(current_counts.values())
            comparison: AnalyticsComparison | None = None
            watermarks = [row.source_watermark_at for row in current_rows]
            if compare == "previous_period":
                previous_from = from_ - timedelta(days=days)
                previous_rows = self.repository.daily_values(
                    scope, previous_from, from_
                )
                complete = complete and self._complete(
                    scope, previous_rows, previous_from, from_
                )
                previous_counts = self._daily_counts(scope, previous_rows)
                previous_summary = self._sum_counts(previous_counts.values())
                comparison = self._comparison(summary_counts, previous_summary)
                watermarks.extend(row.source_watermark_at for row in previous_rows)
            response = AnalyticsResponse(
                organization_id=organization_id,
                bot_id=bot_id,
                reporting_timezone=scope.timezone,
                from_=from_,
                to=to,
                group_by=group_by,
                complete=complete,
                source_watermark_at=min(watermarks) if watermarks else None,
                series=series,
                summary=_metrics(summary_counts),
                comparison=comparison,
            )
        except Exception as exc:
            result = getattr(exc, "safe_code", "ANALYTICS_UNAVAILABLE")
            self._record("analytics_requests_total", "query", str(result), started)
            self.logger.warning(
                "analytics_query_failed", operation="query", result=str(result)
            )
            raise
        self._record("analytics_requests_total", "query", "success", started)
        return response

    def export_csv(
        self,
        organization_id: UUID,
        actor: User,
        *,
        bot_id: UUID | None,
        from_: date,
        to: date,
        group_by: AnalyticsGroupBy,
    ) -> str:
        started = perf_counter()
        try:
            require_scoped_permission(actor, "analytics.export", organization_id)
        except AuthorizationError as exc:
            raise AnalyticsForbidden("permission denied") from exc
        if self.plan_enforcement is not None:
            self.plan_enforcement.require_feature(organization_id, "analytics_export")
        response = self.query(
            organization_id,
            actor,
            bot_id=bot_id,
            from_=from_,
            to=to,
            group_by=group_by,
            compare=None,
        )
        if not response.complete:
            raise AnalyticsDataIncomplete("analytics data is incomplete")
        columns = (
            "period_start",
            "period_end",
            "conversations_started",
            "conversations_closed",
            "handoffs_created",
            "handoffs_resolved",
            "handoff_average_resolution_seconds",
            "automation_executions_created",
            "automation_succeeded",
            "automation_failed",
            "automation_skipped",
            "automation_cancelled",
            "automation_success_rate",
            "contacts_created",
        )
        lines = [",".join(columns)]
        for point in response.series:
            values = point.metrics.model_dump()
            lines.append(
                ",".join(
                    [
                        point.period_start.isoformat(),
                        point.period_end.isoformat(),
                        *(
                            "" if values[column] is None else str(values[column])
                            for column in columns[2:]
                        ),
                    ]
                )
            )
        self._record("analytics_export_total", "csv", "success", started)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _complete(
        scope: AnalyticsScope,
        rows: list[AnalyticsDailyValue],
        from_: date,
        to: date,
    ) -> bool:
        available = {
            (row.local_date, row.bot_id)
            for row in rows
            if row.timezone == scope.timezone
        }
        current = from_
        while current < to:
            if (current, None) not in available:
                return False
            _, bucket_end = AnalyticsProjectionService._bucket(scope.timezone, current)
            expected_bot_ids = (
                (scope.bot_id,)
                if scope.bot_id is not None
                else tuple(bot.bot_id for bot in scope.bots)
            )
            if any(
                AnalyticsProjectionService._bot_expected(scope, bot_id, bucket_end)
                and (current, bot_id) not in available
                for bot_id in expected_bot_ids
            ):
                return False
            current += timedelta(days=1)
        return True

    @staticmethod
    def _daily_counts(
        scope: AnalyticsScope, rows: list[AnalyticsDailyValue]
    ) -> dict[date, dict[str, int]]:
        result: dict[date, dict[str, int]] = defaultdict(_empty_counts)
        bucket_ends: dict[date, datetime] = {}
        for row in rows:
            if row.timezone != scope.timezone:
                continue
            if row.bot_id is None:
                _add(result[row.local_date], row.counts, contacts=True)
            elif scope.bot_id is None or row.bot_id == scope.bot_id:
                bucket_end = bucket_ends.get(row.local_date)
                if bucket_end is None:
                    _, bucket_end = AnalyticsProjectionService._bucket(
                        scope.timezone, row.local_date
                    )
                    bucket_ends[row.local_date] = bucket_end
                if AnalyticsProjectionService._bot_expected(
                    scope, row.bot_id, bucket_end
                ):
                    _add(result[row.local_date], row.counts, contacts=False)
        return dict(result)

    @staticmethod
    def _series(
        daily: dict[date, dict[str, int]],
        from_: date,
        to: date,
        group_by: AnalyticsGroupBy,
    ) -> list[AnalyticsSeriesPoint]:
        buckets: dict[date, dict[str, int]] = defaultdict(_empty_counts)
        current = from_
        while current < to:
            if group_by == "day":
                bucket = current
            elif group_by == "week":
                bucket = current - timedelta(days=current.weekday())
            else:
                bucket = current.replace(day=1)
            source = daily.get(current, _empty_counts())
            for field in _COUNT_FIELDS:
                buckets[bucket][field] += source[field]
            current += timedelta(days=1)
        points: list[AnalyticsSeriesPoint] = []
        for start in sorted(buckets):
            if group_by == "day":
                natural_end = start + timedelta(days=1)
            elif group_by == "week":
                natural_end = start + timedelta(days=7)
            else:
                natural_end = (
                    start.replace(year=start.year + 1, month=1)
                    if start.month == 12
                    else start.replace(month=start.month + 1)
                )
            points.append(
                AnalyticsSeriesPoint(
                    period_start=max(start, from_),
                    period_end=min(natural_end, to),
                    metrics=_metrics(buckets[start]),
                )
            )
        return points

    @staticmethod
    def _sum_counts(values: Iterable[dict[str, int]]) -> dict[str, int]:
        total = _empty_counts()
        for value in values:
            for field in _COUNT_FIELDS:
                total[field] += int(value[field])
        return total

    @staticmethod
    def _comparison(
        current_counts: dict[str, int], previous_counts: dict[str, int]
    ) -> AnalyticsComparison:
        current = _metrics(current_counts)
        previous = _metrics(previous_counts)
        current_values = current.model_dump()
        previous_values = previous.model_dump()
        changes: dict[str, AnalyticsMetricChange] = {}
        for name, current_value in current_values.items():
            previous_value = previous_values[name]
            if current_value is None or previous_value is None:
                continue
            absolute = float(current_value) - float(previous_value)
            if float(previous_value) > 0:
                percent = absolute / float(previous_value)
            elif float(current_value) == 0:
                percent = 0.0
            else:
                percent = None
            changes[name] = AnalyticsMetricChange(
                absolute_change=absolute, percent_change=percent
            )
        return AnalyticsComparison(current=current, previous=previous, change=changes)

    def _record(self, metric: str, operation: str, result: str, started: float) -> None:
        self.metrics.record(
            metric, operation, result, int((perf_counter() - started) * 1000)
        )
