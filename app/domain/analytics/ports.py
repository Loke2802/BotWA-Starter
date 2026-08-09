from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.domain.analytics.contracts import AnalyticsCounts


@dataclass(frozen=True)
class AnalyticsBotLifecycle:
    bot_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class AnalyticsScope:
    organization_id: UUID
    bot_id: UUID | None
    timezone: str
    bots: tuple[AnalyticsBotLifecycle, ...]


@dataclass(frozen=True)
class AnalyticsDailyValue:
    local_date: date
    bot_id: UUID | None
    timezone: str
    counts: AnalyticsCounts
    source_watermark_at: datetime
    computed_at: datetime


class AnalyticsRepository(Protocol):
    def scope(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> AnalyticsScope | None: ...

    def aggregate_sources(
        self,
        scope: AnalyticsScope,
        local_date: date,
        day_start: datetime,
        day_end: datetime,
        source_watermark_at: datetime,
    ) -> AnalyticsCounts: ...

    def upsert_day(
        self,
        scope: AnalyticsScope,
        local_date: date,
        counts: AnalyticsCounts,
        source_watermark_at: datetime,
        computed_at: datetime,
    ) -> None: ...

    def daily_values(
        self, scope: AnalyticsScope, from_: date, to: date
    ) -> list[AnalyticsDailyValue]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
