from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CalendarStatus = Literal["draft", "active", "inactive", "archived"]
CalendarTransition = Literal["activate", "deactivate", "archive"]
ResolutionState = Literal["open", "closed"]
WinningRuleType = Literal[
    "manual_override",
    "date_exception",
    "holiday",
    "weekly_schedule",
    "default_closed",
]
DateExceptionMode = Literal[
    "closed_all_day",
    "open_all_day",
    "replace",
    "add_open",
    "close_partial",
]
HolidayScope = Literal["full_day", "partial"]
HolidaySource = Literal["manual", "external_import"]
OverrideDecision = Literal["open", "closed"]


def _validate_timezone_name(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA name") from exc
    return value


class LocalTimeInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$")

    @model_validator(mode="after")
    def validate_interval(self) -> "LocalTimeInterval":
        if self.start_minute >= self.end_minute:
            raise ValueError(
                "interval start must precede end; normalize midnight crossings"
            )
        return self

    @property
    def start_minute(self) -> int:
        hour, minute = (int(part) for part in self.start.split(":"))
        return hour * 60 + minute

    @property
    def end_minute(self) -> int:
        hour, minute = (int(part) for part in self.end.split(":"))
        return hour * 60 + minute


def _validate_non_overlapping(intervals: list[LocalTimeInterval]) -> None:
    ordered = sorted(intervals, key=lambda item: (item.start_minute, item.end_minute))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.start_minute < previous.end_minute:
            raise ValueError("local intervals cannot overlap")


class WeeklyDayInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weekday: int = Field(ge=1, le=7)
    intervals: list[LocalTimeInterval] = Field(default_factory=list, max_length=16)

    @field_validator("intervals")
    @classmethod
    def intervals_do_not_overlap(
        cls, value: list[LocalTimeInterval]
    ) -> list[LocalTimeInterval]:
        _validate_non_overlapping(value)
        return value


class WeeklyScheduleReplace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    days: list[WeeklyDayInput] = Field(max_length=7)

    @field_validator("days")
    @classmethod
    def weekdays_are_unique(cls, value: list[WeeklyDayInput]) -> list[WeeklyDayInput]:
        weekdays = [day.weekday for day in value]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("weekly schedule weekdays must be unique")
        return value


class BusinessCalendarCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    bot_id: UUID | None = None
    timezone: str = Field(min_length=1, max_length=100)

    _timezone = field_validator("timezone")(_validate_timezone_name)


class BusinessCalendarUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    bot_id: UUID | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def timezone_is_iana(cls, value: str | None) -> str | None:
        return _validate_timezone_name(value) if value is not None else value


class BusinessCalendarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    organization_id: UUID
    bot_id: UUID | None
    name: str
    description: str | None
    timezone: str
    status: CalendarStatus
    version: int
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    deactivated_at: datetime | None
    archived_at: datetime | None


class BusinessCalendarListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[BusinessCalendarResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class WeeklyIntervalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    weekday: int
    interval: LocalTimeInterval


class WeeklyScheduleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    calendar_id: UUID
    calendar_version: int
    days: list[WeeklyDayInput]


class DateExceptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_date: date
    mode: DateExceptionMode
    intervals: list[LocalTimeInterval] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_mode(self) -> "DateExceptionCreate":
        all_day = self.mode in {"closed_all_day", "open_all_day"}
        if all_day and self.intervals:
            raise ValueError("all-day exceptions cannot include intervals")
        if not all_day and not self.intervals:
            raise ValueError("partial and replacement exceptions require intervals")
        _validate_non_overlapping(self.intervals)
        return self


class DateExceptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    mode: DateExceptionMode
    intervals: list[LocalTimeInterval] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_mode(self) -> "DateExceptionUpdate":
        DateExceptionCreate(
            local_date=date.min,
            mode=self.mode,
            intervals=self.intervals,
        )
        return self


class DateExceptionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    calendar_id: UUID
    local_date: date
    mode: DateExceptionMode
    intervals: list[LocalTimeInterval]
    version: int
    created_at: datetime
    updated_at: datetime


class DateExceptionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[DateExceptionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class HolidayCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_date: date
    name: str = Field(min_length=1, max_length=160)
    scope: HolidayScope = "full_day"
    intervals: list[LocalTimeInterval] = Field(default_factory=list, max_length=32)
    source: HolidaySource = "manual"
    external_reference: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_scope(self) -> "HolidayCreate":
        if self.scope == "full_day" and self.intervals:
            raise ValueError("full-day holidays cannot include intervals")
        if self.scope == "partial" and not self.intervals:
            raise ValueError("partial holidays require intervals")
        if self.source == "manual" and self.external_reference is not None:
            raise ValueError("manual holidays cannot include external reference")
        if self.source == "external_import" and self.external_reference is None:
            raise ValueError("imported holidays require external reference")
        _validate_non_overlapping(self.intervals)
        return self


class HolidayUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    scope: HolidayScope
    intervals: list[LocalTimeInterval] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_scope(self) -> "HolidayUpdate":
        if self.scope == "full_day" and self.intervals:
            raise ValueError("full-day holidays cannot include intervals")
        if self.scope == "partial" and not self.intervals:
            raise ValueError("partial holidays require intervals")
        _validate_non_overlapping(self.intervals)
        return self


class HolidayResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    calendar_id: UUID
    local_date: date
    name: str
    scope: HolidayScope
    intervals: list[LocalTimeInterval]
    source: HolidaySource
    version: int
    created_at: datetime
    updated_at: datetime


class HolidayListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[HolidayResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ManualOverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: OverrideDecision
    starts_at: datetime
    ends_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_window(self) -> "ManualOverrideCreate":
        if self.starts_at.tzinfo is None:
            raise ValueError("override start must include an offset or timezone")
        if self.ends_at is not None:
            if self.ends_at.tzinfo is None:
                raise ValueError("override end must include an offset or timezone")
            if self.starts_at >= self.ends_at:
                raise ValueError("override start must precede end")
        return self


class ManualOverrideRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)


class ManualOverrideResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    calendar_id: UUID
    decision: OverrideDecision
    starts_at: datetime
    ends_at: datetime | None
    reason: str
    version: int
    revoked_at: datetime | None
    created_at: datetime


class ManualOverrideListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[ManualOverrideResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class BusinessHoursResolutionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    calendar_id: UUID
    state: ResolutionState
    evaluated_at: datetime
    timezone: str
    local_date: date
    local_time: time
    local_fold: int
    winning_rule_type: WinningRuleType
    winning_rule_id: UUID | None
    calendar_version: int
    next_change_at: datetime | None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    calendar_id: UUID
    resource_type: str
    resource_id: UUID
    action: str
    actor_id: UUID
    previous_version: int | None
    new_version: int
    changes: dict[str, object]
    correlation_id: UUID
    created_at: datetime


class AuditEventListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ImportedCalendarRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_reference: str = Field(min_length=1, max_length=500)
    local_date: date
    name: str = Field(min_length=1, max_length=160)
    scope: HolidayScope
    intervals: list[LocalTimeInterval] = Field(default_factory=list, max_length=32)
