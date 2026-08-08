from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.business_calendar.contracts import (
    BusinessHoursResolutionResponse,
    DateExceptionMode,
    HolidayScope,
    OverrideDecision,
    WinningRuleType,
)
from app.domain.business_calendar.errors import (
    LocalTimeAmbiguous,
    LocalTimeNonexistent,
    TimezoneInvalid,
)


@dataclass(frozen=True)
class CanonicalInterval:
    id: UUID
    start_minute: int
    end_minute: int

    def contains(self, minute: int) -> bool:
        return self.start_minute <= minute < self.end_minute


@dataclass(frozen=True)
class CanonicalDateException:
    id: UUID
    local_date: date
    mode: DateExceptionMode
    intervals: tuple[CanonicalInterval, ...]


@dataclass(frozen=True)
class CanonicalHoliday:
    id: UUID
    local_date: date
    scope: HolidayScope
    intervals: tuple[CanonicalInterval, ...]


@dataclass(frozen=True)
class CanonicalOverride:
    id: UUID
    decision: OverrideDecision
    starts_at: datetime
    ends_at: datetime | None
    version: int
    created_at: datetime
    revoked_at: datetime | None

    def active_at(self, instant: datetime) -> bool:
        return (
            self.revoked_at is None
            and self.starts_at <= instant
            and (self.ends_at is None or instant < self.ends_at)
        )


@dataclass(frozen=True)
class ResolutionCalendar:
    id: UUID
    timezone: str
    version: int


@dataclass(frozen=True)
class ResolutionRules:
    weekly: dict[int, tuple[CanonicalInterval, ...]]
    exceptions: tuple[CanonicalDateException, ...]
    holidays: tuple[CanonicalHoliday, ...]
    overrides: tuple[CanonicalOverride, ...]


@dataclass(frozen=True)
class _Decision:
    state: OverrideDecision
    rule_type: WinningRuleType
    rule_id: UUID | None


def zone_info(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TimezoneInvalid("timezone is invalid") from exc


def localize_strict(
    naive: datetime, timezone_name: str, *, fold: int | None = None
) -> datetime:
    if naive.tzinfo is not None:
        raise ValueError("localize_strict requires a naive datetime")
    zone = zone_info(timezone_name)
    candidates: list[datetime] = []
    for candidate_fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=candidate_fold)
        roundtrip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if roundtrip == naive and all(
            aware.utcoffset() != existing.utcoffset() for existing in candidates
        ):
            candidates.append(aware)
    if not candidates:
        raise LocalTimeNonexistent("local datetime does not exist")
    if len(candidates) > 1 and fold is None:
        raise LocalTimeAmbiguous("local datetime is ambiguous")
    if fold is not None:
        for candidate in candidates:
            if candidate.fold == fold:
                return candidate
        raise LocalTimeAmbiguous("requested fold is invalid")
    return candidates[0]


class BusinessHoursResolver:
    def resolve(
        self,
        calendar: ResolutionCalendar,
        rules: ResolutionRules,
        evaluated_at: datetime,
    ) -> BusinessHoursResolutionResponse:
        if evaluated_at.tzinfo is None:
            raise ValueError("resolution instant must be timezone-aware")
        instant = evaluated_at.astimezone(UTC)
        zone = zone_info(calendar.timezone)
        local = instant.astimezone(zone)
        decision = self._decision(rules, instant, local)
        return BusinessHoursResolutionResponse(
            calendar_id=calendar.id,
            state=decision.state,
            evaluated_at=instant,
            timezone=calendar.timezone,
            local_date=local.date(),
            local_time=local.timetz().replace(tzinfo=None),
            local_fold=local.fold,
            winning_rule_type=decision.rule_type,
            winning_rule_id=decision.rule_id,
            calendar_version=calendar.version,
            next_change_at=self._next_change(rules, instant, zone, decision.state),
        )

    def _decision(
        self, rules: ResolutionRules, instant: datetime, local: datetime
    ) -> _Decision:
        active_overrides = [
            override for override in rules.overrides if override.active_at(instant)
        ]
        if active_overrides:
            highest_version = max(item.version for item in active_overrides)
            versioned = [
                item for item in active_overrides if item.version == highest_version
            ]
            closed = [item for item in versioned if item.decision == "closed"]
            winner = max(
                closed or versioned,
                key=lambda item: (item.created_at, str(item.id)),
            )
            return _Decision(winner.decision, "manual_override", winner.id)

        minute = local.hour * 60 + local.minute
        exception = next(
            (item for item in rules.exceptions if item.local_date == local.date()),
            None,
        )
        if exception is not None:
            if exception.mode == "closed_all_day":
                return _Decision("closed", "date_exception", exception.id)
            if exception.mode == "open_all_day":
                return _Decision("open", "date_exception", exception.id)
            matching = next(
                (item for item in exception.intervals if item.contains(minute)), None
            )
            if exception.mode == "replace":
                return _Decision(
                    "open" if matching else "closed",
                    "date_exception",
                    exception.id,
                )
            if exception.mode == "add_open" and matching is not None:
                return _Decision("open", "date_exception", exception.id)
            if exception.mode == "close_partial" and matching is not None:
                return _Decision("closed", "date_exception", exception.id)

        holidays = [item for item in rules.holidays if item.local_date == local.date()]
        for holiday in sorted(holidays, key=lambda item: str(item.id)):
            if holiday.scope == "full_day" or any(
                interval.contains(minute) for interval in holiday.intervals
            ):
                return _Decision("closed", "holiday", holiday.id)

        weekly = rules.weekly.get(local.isoweekday(), ())
        matching_weekly = next((item for item in weekly if item.contains(minute)), None)
        if matching_weekly is not None:
            return _Decision("open", "weekly_schedule", matching_weekly.id)
        return _Decision("closed", "default_closed", None)

    def _next_change(
        self,
        rules: ResolutionRules,
        instant: datetime,
        zone: ZoneInfo,
        current_state: OverrideDecision,
    ) -> datetime | None:
        candidates: set[datetime] = set()
        horizon = instant + timedelta(days=8)
        for override in rules.overrides:
            for boundary in (override.starts_at, override.ends_at):
                if boundary is not None:
                    normalized = boundary.astimezone(UTC)
                    if instant < normalized <= horizon:
                        candidates.add(normalized)

        local_start = instant.astimezone(zone).date()
        exception_by_date = {item.local_date: item for item in rules.exceptions}
        holidays_by_date: dict[date, list[CanonicalHoliday]] = {}
        for holiday in rules.holidays:
            holidays_by_date.setdefault(holiday.local_date, []).append(holiday)
        for day_offset in range(9):
            local_date = local_start + timedelta(days=day_offset)
            minutes = {0}
            for interval in rules.weekly.get(local_date.isoweekday(), ()):
                minutes.update((interval.start_minute, interval.end_minute))
            exception = exception_by_date.get(local_date)
            if exception is not None:
                for interval in exception.intervals:
                    minutes.update((interval.start_minute, interval.end_minute))
            for holiday in holidays_by_date.get(local_date, []):
                for interval in holiday.intervals:
                    minutes.update((interval.start_minute, interval.end_minute))
            for minute in minutes:
                boundary_date = local_date
                boundary_minute = minute
                if minute == 1440:
                    boundary_date += timedelta(days=1)
                    boundary_minute = 0
                naive = datetime.combine(
                    boundary_date,
                    time(boundary_minute // 60, boundary_minute % 60),
                )
                for fold in (0, 1):
                    try:
                        candidate = localize_strict(
                            naive, zone.key, fold=fold
                        ).astimezone(UTC)
                    except (LocalTimeAmbiguous, LocalTimeNonexistent):
                        continue
                    if instant < candidate <= horizon:
                        candidates.add(candidate)

        for candidate in sorted(candidates):
            local = candidate.astimezone(zone)
            if self._decision(rules, candidate, local).state != current_state:
                return candidate
        return None
