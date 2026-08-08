from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from app.domain.access.contracts import ROLE_PERMISSIONS
from app.domain.business_calendar.contracts import (
    BusinessCalendarCreate,
    DateExceptionCreate,
    LocalTimeInterval,
    WeeklyDayInput,
    WeeklyScheduleReplace,
)
from app.domain.business_calendar.errors import (
    LocalTimeAmbiguous,
    LocalTimeNonexistent,
)
from app.domain.business_calendar.resolver import (
    BusinessHoursResolver,
    CanonicalDateException,
    CanonicalHoliday,
    CanonicalInterval,
    CanonicalOverride,
    ResolutionCalendar,
    ResolutionRules,
    localize_strict,
)
from pydantic import ValidationError


def _interval(start: int, end: int) -> CanonicalInterval:
    return CanonicalInterval(uuid4(), start, end)


def test_contracts_validate_iana_timezone_normalized_intervals_and_overlap() -> None:
    calendar = BusinessCalendarCreate(name="Support", timezone="America/Lima")
    assert calendar.timezone == "America/Lima"
    assert LocalTimeInterval(start="22:00", end="24:00").end_minute == 1440

    with pytest.raises(ValidationError):
        BusinessCalendarCreate(name="Invalid", timezone="UTC-5")
    with pytest.raises(ValidationError):
        LocalTimeInterval(start="22:00", end="02:00")
    with pytest.raises(ValidationError):
        WeeklyScheduleReplace(
            expected_version=1,
            days=[
                WeeklyDayInput(
                    weekday=1,
                    intervals=[
                        LocalTimeInterval(start="09:00", end="12:00"),
                        LocalTimeInterval(start="11:00", end="13:00"),
                    ],
                )
            ],
        )
    with pytest.raises(ValidationError):
        DateExceptionCreate(
            local_date=date(2026, 8, 10),
            mode="closed_all_day",
            intervals=[LocalTimeInterval(start="09:00", end="10:00")],
        )


def test_resolver_applies_manual_exception_holiday_weekly_precedence() -> None:
    calendar_id = uuid4()
    weekly_id = uuid4()
    exception_id = uuid4()
    holiday_id = uuid4()
    override_id = uuid4()
    resolver = BusinessHoursResolver()
    rules = ResolutionRules(
        weekly={1: (CanonicalInterval(weekly_id, 9 * 60, 17 * 60),)},
        exceptions=(
            CanonicalDateException(
                exception_id,
                date(2026, 8, 10),
                "open_all_day",
                (),
            ),
        ),
        holidays=(CanonicalHoliday(holiday_id, date(2026, 8, 10), "full_day", ()),),
        overrides=(
            CanonicalOverride(
                override_id,
                "closed",
                datetime(2026, 8, 10, 9, tzinfo=UTC),
                datetime(2026, 8, 10, 11, tzinfo=UTC),
                4,
                datetime(2026, 8, 10, 8, tzinfo=UTC),
                None,
            ),
        ),
    )
    calendar = ResolutionCalendar(calendar_id, "UTC", 4)

    during_override = resolver.resolve(
        calendar, rules, datetime(2026, 8, 10, 10, tzinfo=UTC)
    )
    assert during_override.state == "closed"
    assert during_override.winning_rule_type == "manual_override"
    assert during_override.winning_rule_id == override_id
    assert during_override.next_change_at == datetime(2026, 8, 10, 11, tzinfo=UTC)

    after_override = resolver.resolve(
        calendar, rules, datetime(2026, 8, 10, 11, tzinfo=UTC)
    )
    assert after_override.state == "open"
    assert after_override.winning_rule_type == "date_exception"
    assert after_override.winning_rule_id == exception_id


def test_resolver_partial_closures_and_default_closed_are_deterministic() -> None:
    calendar = ResolutionCalendar(uuid4(), "UTC", 2)
    holiday_id = uuid4()
    weekly_id = uuid4()
    rules = ResolutionRules(
        weekly={1: (CanonicalInterval(weekly_id, 9 * 60, 17 * 60),)},
        exceptions=(),
        holidays=(
            CanonicalHoliday(
                holiday_id,
                date(2026, 8, 10),
                "partial",
                (_interval(12 * 60, 13 * 60),),
            ),
        ),
        overrides=(),
    )

    before = BusinessHoursResolver().resolve(
        calendar, rules, datetime(2026, 8, 10, 11, 59, tzinfo=UTC)
    )
    closed = BusinessHoursResolver().resolve(
        calendar, rules, datetime(2026, 8, 10, 12, tzinfo=UTC)
    )
    after = BusinessHoursResolver().resolve(
        calendar, rules, datetime(2026, 8, 10, 13, tzinfo=UTC)
    )
    outside = BusinessHoursResolver().resolve(
        calendar, rules, datetime(2026, 8, 10, 17, tzinfo=UTC)
    )

    assert (before.state, before.winning_rule_type) == ("open", "weekly_schedule")
    assert (closed.state, closed.winning_rule_type) == ("closed", "holiday")
    assert (after.state, after.winning_rule_type) == ("open", "weekly_schedule")
    assert (outside.state, outside.winning_rule_type) == (
        "closed",
        "default_closed",
    )


def test_dst_localization_rejects_nonexistent_and_requires_fold_for_ambiguous() -> None:
    with pytest.raises(LocalTimeNonexistent):
        localize_strict(datetime(2026, 3, 8, 2, 30), "America/New_York")
    with pytest.raises(LocalTimeAmbiguous):
        localize_strict(datetime(2026, 11, 1, 1, 30), "America/New_York")

    first = localize_strict(datetime(2026, 11, 1, 1, 30), "America/New_York", fold=0)
    second = localize_strict(datetime(2026, 11, 1, 1, 30), "America/New_York", fold=1)
    assert first.astimezone(UTC) != second.astimezone(UTC)


def test_resolver_preserves_dst_fold_and_is_deterministic() -> None:
    interval_id = uuid4()
    calendar = ResolutionCalendar(uuid4(), "America/New_York", 7)
    rules = ResolutionRules(
        weekly={7: (CanonicalInterval(interval_id, 60, 120),)},
        exceptions=(),
        holidays=(),
        overrides=(),
    )
    resolver = BusinessHoursResolver()

    first = resolver.resolve(calendar, rules, datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
    repeated = resolver.resolve(
        calendar, rules, datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    )
    second = resolver.resolve(calendar, rules, datetime(2026, 11, 1, 6, 30, tzinfo=UTC))

    assert first == repeated
    assert (first.state, first.local_fold) == ("open", 0)
    assert (second.state, second.local_fold) == ("open", 1)
    assert first.winning_rule_id == second.winning_rule_id == interval_id


def test_midnight_normalization_and_half_open_boundaries() -> None:
    monday_id, tuesday_id = uuid4(), uuid4()
    calendar = ResolutionCalendar(uuid4(), "UTC", 3)
    rules = ResolutionRules(
        weekly={
            1: (CanonicalInterval(monday_id, 22 * 60, 24 * 60),),
            2: (CanonicalInterval(tuesday_id, 0, 2 * 60),),
        },
        exceptions=(),
        holidays=(),
        overrides=(),
    )
    resolver = BusinessHoursResolver()

    monday = resolver.resolve(
        calendar, rules, datetime(2026, 8, 10, 23, 59, tzinfo=UTC)
    )
    midnight = resolver.resolve(
        calendar, rules, datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
    )
    end = resolver.resolve(calendar, rules, datetime(2026, 8, 11, 2, 0, tzinfo=UTC))

    assert (monday.state, monday.winning_rule_id) == ("open", monday_id)
    assert monday.next_change_at == datetime(2026, 8, 11, 2, tzinfo=UTC)
    assert (midnight.state, midnight.winning_rule_id) == ("open", tuesday_id)
    assert (end.state, end.winning_rule_type) == ("closed", "default_closed")


def test_prd015_permissions_apply_minimum_operator_access() -> None:
    administrative = {
        "business_calendar.create",
        "business_calendar.update",
        "business_calendar.activate",
        "business_calendar.deactivate",
        "business_calendar.archive",
        "business_calendar.schedule.manage",
        "business_calendar.exception.manage",
        "business_calendar.holiday.manage",
        "business_calendar.override.manage",
    }
    assert administrative.issubset(ROLE_PERMISSIONS["organization_owner"])
    assert administrative.issubset(ROLE_PERMISSIONS["organization_admin"])
    assert {
        "business_calendar.read",
        "business_calendar.resolve",
    }.issubset(ROLE_PERMISSIONS["operator"])
    assert not administrative.intersection(ROLE_PERMISSIONS["operator"])
    assert not {
        "business_calendar.read",
        "business_calendar.resolve",
    }.intersection(ROLE_PERMISSIONS["viewer"])


def test_migration_declares_single_prd015_revision_and_all_tables() -> None:
    migration = Path(
        "alembic/versions/20260808_0016_create_business_calendar_tables.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260808_0016"' in migration
    assert 'down_revision = "20260807_0015"' in migration
    for table in (
        "business_calendar",
        "business_calendar_weekly_interval",
        "business_calendar_date_exception",
        "business_calendar_holiday",
        "business_calendar_override",
        "business_calendar_idempotency_receipt",
        "business_calendar_audit_event",
    ):
        assert f'"{table}"' in migration
        assert f'op.drop_table("{table}")' in migration
