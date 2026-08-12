import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import TypeVar, cast
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, TypeAdapter
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.business_calendar.clock import SystemClock
from app.application.business_calendar.metrics import BusinessCalendarMetrics
from app.application.plans.service import PlanEnforcementService
from app.domain.access.contracts import Permission
from app.domain.audit.contracts import (
    AuditAction,
    AuditChangedField,
    AuditMetadata,
    ChangedFieldsMetadata,
    EmptyMetadata,
    StatusTransitionMetadata,
)
from app.domain.audit.ports import AuditWriter
from app.domain.business_calendar.contracts import (
    AuditEventResponse,
    BusinessCalendarCreate,
    BusinessCalendarResponse,
    BusinessCalendarUpdate,
    BusinessHoursResolutionResponse,
    CalendarStatus,
    CalendarTransition,
    DateExceptionCreate,
    DateExceptionMode,
    DateExceptionResponse,
    DateExceptionUpdate,
    HolidayCreate,
    HolidayResponse,
    HolidayScope,
    HolidayUpdate,
    LocalTimeInterval,
    ManualOverrideCreate,
    ManualOverrideResponse,
    ManualOverrideRevoke,
    OverrideDecision,
    WeeklyDayInput,
    WeeklyScheduleReplace,
    WeeklyScheduleResponse,
)
from app.domain.business_calendar.errors import (
    BusinessCalendarConflict,
    BusinessCalendarForbidden,
    BusinessCalendarInactive,
    BusinessCalendarNotFound,
    BusinessCalendarPersistenceError,
    IdempotencyConflict,
    ScheduleValidationError,
    ScheduleVersionConflict,
)
from app.domain.business_calendar.ports import Clock
from app.domain.business_calendar.resolver import (
    BusinessHoursResolver,
    CanonicalDateException,
    CanonicalHoliday,
    CanonicalInterval,
    CanonicalOverride,
    ResolutionCalendar,
    ResolutionRules,
    zone_info,
)
from app.domain.user.contracts import User
from app.infrastructure.models.business_calendar import (
    BusinessCalendarAuditEventModel,
    BusinessCalendarDateExceptionModel,
    BusinessCalendarHolidayModel,
    BusinessCalendarIdempotencyReceiptModel,
    BusinessCalendarModel,
    BusinessCalendarOverrideModel,
    BusinessCalendarWeeklyIntervalModel,
)
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.security.authorization import AuthorizationError, require_scoped_permission

ResponseT = TypeVar("ResponseT", bound=BaseModel)
AUDIT_CHANGED_FIELD_ADAPTER: TypeAdapter[AuditChangedField] = TypeAdapter(
    AuditChangedField
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _minute_text(value: int) -> str:
    if value == 1440:
        return "24:00"
    return f"{value // 60:02d}:{value % 60:02d}"


def _interval_payload(intervals: list[LocalTimeInterval]) -> list[dict[str, int]]:
    return [
        {"start_minute": item.start_minute, "end_minute": item.end_minute}
        for item in intervals
    ]


def _interval_contracts(raw: object) -> list[LocalTimeInterval]:
    if not isinstance(raw, list):
        raise ScheduleValidationError("stored intervals are invalid")
    values: list[LocalTimeInterval] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ScheduleValidationError("stored intervals are invalid")
        start = item.get("start_minute")
        end = item.get("end_minute")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ScheduleValidationError("stored intervals are invalid")
        try:
            values.append(
                LocalTimeInterval(start=_minute_text(start), end=_minute_text(end))
            )
        except ValueError as exc:
            raise ScheduleValidationError("stored intervals are invalid") from exc
    return values


class BusinessCalendarService:
    def __init__(
        self,
        repository: BusinessCalendarRepository,
        session: Session,
        audit_writer: AuditWriter,
        *,
        resolver: BusinessHoursResolver | None = None,
        clock: Clock | None = None,
        metrics: BusinessCalendarMetrics | None = None,
        plan_enforcement: "PlanEnforcementService",
    ) -> None:
        self.repository = repository
        self.session = session
        self.resolver = resolver or BusinessHoursResolver()
        self.clock = clock or SystemClock()
        self.metrics = metrics or BusinessCalendarMetrics()
        self.logger = structlog.get_logger(__name__)
        self.audit_writer = audit_writer
        self.plan_enforcement = plan_enforcement

    @staticmethod
    def _authorize(actor: User, permission: Permission, organization_id: UUID) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise BusinessCalendarForbidden("business calendar access denied") from exc

    def _calendar(
        self, organization_id: UUID, calendar_id: UUID, *, lock: bool = False
    ) -> BusinessCalendarModel:
        row = self.repository.calendar(organization_id, calendar_id, lock=lock)
        if row is None:
            raise BusinessCalendarNotFound("business calendar not found")
        return row

    @staticmethod
    def _ensure_mutable(row: BusinessCalendarModel) -> None:
        if row.status == "archived":
            raise BusinessCalendarConflict("archived calendar is terminal")

    def _check_version(self, actual: int, expected: int) -> None:
        if actual != expected:
            self.metrics.record_version_conflict()
            raise ScheduleVersionConflict("resource version does not match")

    def _validate_date_range(
        self, date_from: date | None, date_to: date | None
    ) -> None:
        if date_from is not None and date_to is not None and date_from > date_to:
            self.metrics.record_validation_error()
            raise ScheduleValidationError("date range is invalid")

    def _validate_pagination(self, offset: int, limit: int) -> None:
        if offset < 0 or not 1 <= limit <= 100:
            self.metrics.record_validation_error()
            raise ScheduleValidationError("pagination is invalid")

    def _validate_bot(self, organization_id: UUID, bot_id: UUID | None) -> None:
        if bot_id is not None and not self.repository.bot_belongs_to(
            organization_id, bot_id
        ):
            self.metrics.record_validation_error()
            raise ScheduleValidationError("bot scope is invalid")

    @staticmethod
    def _idempotency_key(key: str | None) -> str | None:
        if key is None:
            return None
        normalized = key.strip()
        if not 8 <= len(normalized) <= 128:
            raise ScheduleValidationError("idempotency key length is invalid")
        return normalized

    @staticmethod
    def _request_hash(command: str, payload: object) -> str:
        encoded = json.dumps(
            {"command": command, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _replay(
        self,
        organization_id: UUID,
        key: str | None,
        command: str,
        request_hash: str,
        response_type: type[ResponseT],
    ) -> ResponseT | None:
        if key is None:
            return None
        receipt = self.repository.idempotency_receipt(organization_id, key, lock=True)
        if receipt is None:
            return None
        if receipt.command_type != command or receipt.request_hash != request_hash:
            raise IdempotencyConflict("idempotency key was used with another request")
        return response_type.model_validate(receipt.response_data)

    def _receipt(
        self,
        organization_id: UUID,
        key: str | None,
        command: str,
        request_hash: str,
        resource_type: str,
        resource_id: UUID,
        response: BaseModel,
    ) -> None:
        if key is None:
            return
        self.repository.add(
            BusinessCalendarIdempotencyReceiptModel(
                organization_id=organization_id,
                idempotency_key=key,
                command_type=command,
                request_hash=request_hash,
                resource_type=resource_type,
                resource_id=resource_id,
                response_data=response.model_dump(mode="json"),
                created_at=self.clock.now(),
            )
        )

    def _audit(
        self,
        row: BusinessCalendarModel,
        *,
        resource_type: str,
        resource_id: UUID,
        action: str,
        actor: User,
        previous_version: int | None,
        new_version: int,
        changes: dict[str, object],
        correlation_id: UUID,
    ) -> None:
        audit_at = self.clock.now()
        self.repository.add(
            BusinessCalendarAuditEventModel(
                organization_id=row.organization_id,
                calendar_id=row.id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                actor_id=actor.id,
                previous_version=previous_version,
                new_version=new_version,
                changes=changes,
                correlation_id=correlation_id,
                created_at=audit_at,
            )
        )
        generic_action, metadata = self._generic_audit_metadata(
            resource_type=resource_type,
            action=action,
            changes=changes,
        )
        append_user_audit(
            self.audit_writer,
            organization_id=row.organization_id,
            actor=actor,
            action=generic_action,
            resource_type="business_calendar",
            resource_id=row.id,
            metadata=metadata,
            correlation_id=correlation_id,
            occurred_at=row.updated_at if row.updated_at is not None else audit_at,
        )

    @staticmethod
    def _generic_audit_metadata(
        *, resource_type: str, action: str, changes: dict[str, object]
    ) -> tuple[AuditAction, AuditMetadata]:
        if action == "calendar.created":
            return "business_calendar.created", EmptyMetadata()
        if action in {
            "calendar.activated",
            "calendar.deactivated",
            "calendar.archived",
        }:
            from_status = changes.get("from_status")
            to_status = changes.get("to_status")
            if not isinstance(from_status, str) or not isinstance(to_status, str):
                raise ScheduleValidationError("calendar audit transition is invalid")
            transition = StatusTransitionMetadata(
                from_status=from_status, to_status=to_status
            )
            action_map: dict[str, AuditAction] = {
                "calendar.activated": "business_calendar.activated",
                "calendar.deactivated": "business_calendar.deactivated",
                "calendar.archived": "business_calendar.archived",
            }
            return action_map[action], transition
        if resource_type == "calendar":
            raw_fields = changes.get("changed_fields", [])
            if not isinstance(raw_fields, list):
                raise ScheduleValidationError("calendar audit fields are invalid")
            fields = tuple(
                AUDIT_CHANGED_FIELD_ADAPTER.validate_python(field)
                for field in raw_fields
            )
        else:
            field_map: dict[str, AuditChangedField] = {
                "weekly_schedule": "weekly_schedule",
                "date_exception": "date_exception",
                "holiday": "holiday",
                "override": "manual_override",
            }
            field = field_map.get(resource_type)
            if field is None:
                raise ScheduleValidationError("calendar audit resource is invalid")
            fields = (field,)
        return "business_calendar.updated", ChangedFieldsMetadata(changed_fields=fields)

    def _commit_result(
        self,
        result: ResponseT,
        *,
        organization_id: UUID,
        key: str | None,
        command: str,
        request_hash: str,
        response_type: type[ResponseT],
    ) -> ResponseT:
        try:
            self.session.commit()
            return result
        except IntegrityError as exc:
            self.session.rollback()
            replay = self._replay(
                organization_id, key, command, request_hash, response_type
            )
            if replay is not None:
                return replay
            raise BusinessCalendarConflict("business calendar write conflicts") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise BusinessCalendarPersistenceError(
                "business calendar persistence failed"
            ) from exc

    def _flush_parent(
        self,
        *,
        organization_id: UUID,
        key: str | None,
        command: str,
        request_hash: str,
        response_type: type[ResponseT],
    ) -> ResponseT | None:
        """Insert a new aggregate root before its FK-bound audit rows."""
        try:
            self.session.flush()
            return None
        except IntegrityError as exc:
            self.session.rollback()
            replay = self._replay(
                organization_id, key, command, request_hash, response_type
            )
            if replay is not None:
                return replay
            raise BusinessCalendarConflict("business calendar write conflicts") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise BusinessCalendarPersistenceError(
                "business calendar persistence failed"
            ) from exc

    @staticmethod
    def _calendar_response(row: BusinessCalendarModel) -> BusinessCalendarResponse:
        return BusinessCalendarResponse.model_validate(row)

    @staticmethod
    def _date_exception_response(
        row: BusinessCalendarDateExceptionModel,
    ) -> DateExceptionResponse:
        return DateExceptionResponse(
            id=row.id,
            calendar_id=row.calendar_id,
            local_date=row.local_date,
            mode=row.mode,
            intervals=_interval_contracts(row.intervals),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _holiday_response(row: BusinessCalendarHolidayModel) -> HolidayResponse:
        return HolidayResponse(
            id=row.id,
            calendar_id=row.calendar_id,
            local_date=row.local_date,
            name=row.name,
            scope=row.scope,
            intervals=_interval_contracts(row.intervals),
            source=row.source,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _override_response(
        row: BusinessCalendarOverrideModel,
    ) -> ManualOverrideResponse:
        return ManualOverrideResponse(
            id=row.id,
            calendar_id=row.calendar_id,
            decision=row.decision,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            reason=row.reason,
            version=row.version,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
        )

    def create_calendar(
        self,
        organization_id: UUID,
        payload: BusinessCalendarCreate,
        actor: User,
        *,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> BusinessCalendarResponse:
        self._authorize(actor, "business_calendar.create", organization_id)
        self._validate_bot(organization_id, payload.bot_id)
        zone_info(payload.timezone)
        key = self._idempotency_key(idempotency_key)
        command = "business_calendar.create"
        request_hash = self._request_hash(command, payload.model_dump(mode="json"))
        replay = self._replay(
            organization_id, key, command, request_hash, BusinessCalendarResponse
        )
        if replay is not None:
            return replay
        self.plan_enforcement.require_consuming_action(
            organization_id,
            feature="business_calendar",
            limit="max_business_calendars",
        )
        now = self.clock.now()
        row = BusinessCalendarModel(
            id=uuid4(),
            organization_id=organization_id,
            bot_id=payload.bot_id,
            name=payload.name,
            description=payload.description,
            timezone=payload.timezone,
            status="draft",
            version=1,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        self.repository.add(row)
        replay_after_race = self._flush_parent(
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=BusinessCalendarResponse,
        )
        if replay_after_race is not None:
            return replay_after_race
        response = self._calendar_response(row)
        correlation = correlation_id or uuid4()
        self._audit(
            row,
            resource_type="calendar",
            resource_id=row.id,
            action="calendar.created",
            actor=actor,
            previous_version=None,
            new_version=1,
            changes={
                "timezone": row.timezone,
                "bot_id": str(row.bot_id) if row.bot_id else None,
            },
            correlation_id=correlation,
        )
        self._receipt(
            organization_id,
            key,
            command,
            request_hash,
            "calendar",
            row.id,
            response,
        )
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=BusinessCalendarResponse,
        )

    def list_calendars(
        self,
        organization_id: UUID,
        actor: User,
        *,
        status: CalendarStatus | None,
        bot_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[BusinessCalendarResponse], int]:
        self._authorize(actor, "business_calendar.read", organization_id)
        self._validate_pagination(offset, limit)
        rows, total = self.repository.calendars(
            organization_id,
            status=status,
            bot_id=bot_id,
            offset=offset,
            limit=limit,
        )
        return [self._calendar_response(row) for row in rows], total

    def get_calendar(
        self, organization_id: UUID, calendar_id: UUID, actor: User
    ) -> BusinessCalendarResponse:
        self._authorize(actor, "business_calendar.read", organization_id)
        return self._calendar_response(self._calendar(organization_id, calendar_id))

    def update_calendar(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        payload: BusinessCalendarUpdate,
        actor: User,
        *,
        correlation_id: UUID | None = None,
    ) -> BusinessCalendarResponse:
        self._authorize(actor, "business_calendar.update", organization_id)
        row = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(row)
        self._check_version(row.version, payload.expected_version)
        if "bot_id" in payload.model_fields_set:
            self._validate_bot(organization_id, payload.bot_id)
            row.bot_id = payload.bot_id
        changed_fields: list[str] = []
        for field in ("name", "description", "timezone"):
            if field not in payload.model_fields_set:
                continue
            value = getattr(payload, field)
            if field in {"name", "timezone"} and value is None:
                raise ScheduleValidationError(f"{field} cannot be null")
            if field == "timezone" and isinstance(value, str):
                zone_info(value)
            setattr(row, field, value)
            changed_fields.append(field)
        if "bot_id" in payload.model_fields_set:
            changed_fields.append("bot_id")
        previous = row.version
        row.version += 1
        row.updated_by_user_id = actor.id
        row.updated_at = self.clock.now()
        self._audit(
            row,
            resource_type="calendar",
            resource_id=row.id,
            action="calendar.updated",
            actor=actor,
            previous_version=previous,
            new_version=row.version,
            changes={"changed_fields": changed_fields},
            correlation_id=correlation_id or uuid4(),
        )
        response = self._calendar_response(row)
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=None,
            command="calendar.update",
            request_hash="",
            response_type=BusinessCalendarResponse,
        )

    def transition_calendar(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        target: CalendarTransition,
        actor: User,
        *,
        correlation_id: UUID | None = None,
    ) -> BusinessCalendarResponse:
        permission: Permission
        if target == "activate":
            permission = "business_calendar.activate"
        elif target == "deactivate":
            permission = "business_calendar.deactivate"
        elif target == "archive":
            permission = "business_calendar.archive"
        else:
            raise ScheduleValidationError("calendar transition is invalid")
        self._authorize(actor, permission, organization_id)
        if target == "activate":
            self.plan_enforcement.require_consuming_action(
                organization_id, feature="business_calendar"
            )
        row = self._calendar(organization_id, calendar_id, lock=True)
        state = {
            "activate": "active",
            "deactivate": "inactive",
            "archive": "archived",
        }[target]
        allowed = {
            "active": {"draft", "inactive"},
            "inactive": {"active"},
            "archived": {"draft", "active", "inactive"},
        }
        if row.status not in allowed[state]:
            raise BusinessCalendarConflict("invalid calendar lifecycle transition")
        previous = row.version
        previous_status = row.status
        now = self.clock.now()
        row.status = state
        row.version += 1
        row.updated_by_user_id = actor.id
        row.updated_at = now
        if state == "active":
            row.activated_at = now
        elif state == "inactive":
            row.deactivated_at = now
        else:
            row.archived_at = now
        self._audit(
            row,
            resource_type="calendar",
            resource_id=row.id,
            action=f"calendar.{target}d",
            actor=actor,
            previous_version=previous,
            new_version=row.version,
            changes={"from_status": previous_status, "to_status": state},
            correlation_id=correlation_id or uuid4(),
        )
        response = self._calendar_response(row)
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=None,
            command=f"calendar.{target}",
            request_hash="",
            response_type=BusinessCalendarResponse,
        )

    def get_weekly_schedule(
        self, organization_id: UUID, calendar_id: UUID, actor: User
    ) -> WeeklyScheduleResponse:
        self._authorize(actor, "business_calendar.read", organization_id)
        row = self._calendar(organization_id, calendar_id)
        return self._weekly_response(row)

    def _weekly_response(self, row: BusinessCalendarModel) -> WeeklyScheduleResponse:
        grouped: dict[int, list[LocalTimeInterval]] = {}
        for interval in self.repository.weekly_intervals(row.organization_id, row.id):
            grouped.setdefault(interval.weekday, []).append(
                LocalTimeInterval(
                    start=_minute_text(interval.start_minute),
                    end=_minute_text(interval.end_minute),
                )
            )
        return WeeklyScheduleResponse(
            calendar_id=row.id,
            calendar_version=row.version,
            days=[
                WeeklyDayInput(weekday=weekday, intervals=intervals)
                for weekday, intervals in sorted(grouped.items())
            ],
        )

    def replace_weekly_schedule(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        payload: WeeklyScheduleReplace,
        actor: User,
        *,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> WeeklyScheduleResponse:
        self._authorize(actor, "business_calendar.schedule.manage", organization_id)
        key = self._idempotency_key(idempotency_key)
        command = f"weekly_schedule.replace:{calendar_id}"
        request_hash = self._request_hash(command, payload.model_dump(mode="json"))
        replay = self._replay(
            organization_id, key, command, request_hash, WeeklyScheduleResponse
        )
        if replay is not None:
            return replay
        row = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(row)
        self._check_version(row.version, payload.expected_version)
        intervals = [
            BusinessCalendarWeeklyIntervalModel(
                organization_id=organization_id,
                calendar_id=calendar_id,
                weekday=day.weekday,
                start_minute=interval.start_minute,
                end_minute=interval.end_minute,
                created_at=self.clock.now(),
            )
            for day in payload.days
            for interval in day.intervals
        ]
        previous = row.version
        row.version += 1
        row.updated_by_user_id = actor.id
        row.updated_at = self.clock.now()
        self.repository.replace_weekly_intervals(
            organization_id, calendar_id, intervals
        )
        response = WeeklyScheduleResponse(
            calendar_id=row.id,
            calendar_version=row.version,
            days=payload.days,
        )
        self._audit(
            row,
            resource_type="weekly_schedule",
            resource_id=row.id,
            action="weekly_schedule.replaced",
            actor=actor,
            previous_version=previous,
            new_version=row.version,
            changes={"day_count": len(payload.days), "interval_count": len(intervals)},
            correlation_id=correlation_id or uuid4(),
        )
        self._receipt(
            organization_id,
            key,
            command,
            request_hash,
            "weekly_schedule",
            row.id,
            response,
        )
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=WeeklyScheduleResponse,
        )

    def create_date_exception(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        payload: DateExceptionCreate,
        actor: User,
        *,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> DateExceptionResponse:
        self._authorize(actor, "business_calendar.exception.manage", organization_id)
        key = self._idempotency_key(idempotency_key)
        command = f"date_exception.create:{calendar_id}"
        request_hash = self._request_hash(command, payload.model_dump(mode="json"))
        replay = self._replay(
            organization_id, key, command, request_hash, DateExceptionResponse
        )
        if replay is not None:
            return replay
        calendar = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(calendar)
        now = self.clock.now()
        row = BusinessCalendarDateExceptionModel(
            id=uuid4(),
            organization_id=organization_id,
            calendar_id=calendar_id,
            local_date=payload.local_date,
            mode=payload.mode,
            intervals=_interval_payload(payload.intervals),
            version=1,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        previous = calendar.version
        calendar.version += 1
        calendar.updated_by_user_id = actor.id
        calendar.updated_at = now
        self.repository.add(row)
        response = self._date_exception_response(row)
        self._audit(
            calendar,
            resource_type="date_exception",
            resource_id=row.id,
            action="date_exception.created",
            actor=actor,
            previous_version=previous,
            new_version=calendar.version,
            changes={
                "local_date": payload.local_date.isoformat(),
                "mode": payload.mode,
            },
            correlation_id=correlation_id or uuid4(),
        )
        self._receipt(
            organization_id,
            key,
            command,
            request_hash,
            "date_exception",
            row.id,
            response,
        )
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=DateExceptionResponse,
        )

    def list_date_exceptions(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DateExceptionResponse], int]:
        self._authorize(actor, "business_calendar.read", organization_id)
        self._calendar(organization_id, calendar_id)
        self._validate_date_range(date_from, date_to)
        self._validate_pagination(offset, limit)
        rows, total = self.repository.date_exceptions(
            organization_id,
            calendar_id,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )
        return [self._date_exception_response(row) for row in rows], total

    def update_date_exception(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        exception_id: UUID,
        payload: DateExceptionUpdate,
        actor: User,
        *,
        correlation_id: UUID | None = None,
    ) -> DateExceptionResponse:
        self._authorize(actor, "business_calendar.exception.manage", organization_id)
        calendar = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(calendar)
        row = self.repository.date_exception(
            organization_id, calendar_id, exception_id, lock=True
        )
        if row is None:
            raise BusinessCalendarNotFound("date exception not found")
        self._check_version(row.version, payload.expected_version)
        previous_calendar = calendar.version
        row.mode = payload.mode
        row.intervals = _interval_payload(payload.intervals)
        row.version += 1
        row.updated_by_user_id = actor.id
        row.updated_at = self.clock.now()
        calendar.version += 1
        calendar.updated_by_user_id = actor.id
        calendar.updated_at = row.updated_at
        self._audit(
            calendar,
            resource_type="date_exception",
            resource_id=row.id,
            action="date_exception.updated",
            actor=actor,
            previous_version=previous_calendar,
            new_version=calendar.version,
            changes={"mode": row.mode, "interval_count": len(row.intervals)},
            correlation_id=correlation_id or uuid4(),
        )
        response = self._date_exception_response(row)
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=None,
            command="date_exception.update",
            request_hash="",
            response_type=DateExceptionResponse,
        )

    def create_holiday(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        payload: HolidayCreate,
        actor: User,
        *,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> HolidayResponse:
        self._authorize(actor, "business_calendar.holiday.manage", organization_id)
        key = self._idempotency_key(idempotency_key)
        command = f"holiday.create:{calendar_id}"
        request_hash = self._request_hash(command, payload.model_dump(mode="json"))
        replay = self._replay(
            organization_id, key, command, request_hash, HolidayResponse
        )
        if replay is not None:
            return replay
        calendar = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(calendar)
        now = self.clock.now()
        external_hash = (
            hashlib.sha256(payload.external_reference.encode("utf-8")).hexdigest()
            if payload.external_reference is not None
            else None
        )
        row = BusinessCalendarHolidayModel(
            id=uuid4(),
            organization_id=organization_id,
            calendar_id=calendar_id,
            local_date=payload.local_date,
            name=payload.name,
            scope=payload.scope,
            intervals=_interval_payload(payload.intervals),
            source=payload.source,
            external_reference_hash=external_hash,
            version=1,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        previous = calendar.version
        calendar.version += 1
        calendar.updated_by_user_id = actor.id
        calendar.updated_at = now
        self.repository.add(row)
        response = self._holiday_response(row)
        self._audit(
            calendar,
            resource_type="holiday",
            resource_id=row.id,
            action="holiday.created",
            actor=actor,
            previous_version=previous,
            new_version=calendar.version,
            changes={
                "local_date": payload.local_date.isoformat(),
                "scope": payload.scope,
                "source": payload.source,
            },
            correlation_id=correlation_id or uuid4(),
        )
        self._receipt(
            organization_id,
            key,
            command,
            request_hash,
            "holiday",
            row.id,
            response,
        )
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=HolidayResponse,
        )

    def list_holidays(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        actor: User,
        *,
        date_from: date | None,
        date_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[HolidayResponse], int]:
        self._authorize(actor, "business_calendar.read", organization_id)
        self._calendar(organization_id, calendar_id)
        self._validate_date_range(date_from, date_to)
        self._validate_pagination(offset, limit)
        rows, total = self.repository.holidays(
            organization_id,
            calendar_id,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=limit,
        )
        return [self._holiday_response(row) for row in rows], total

    def update_holiday(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        holiday_id: UUID,
        payload: HolidayUpdate,
        actor: User,
        *,
        correlation_id: UUID | None = None,
    ) -> HolidayResponse:
        self._authorize(actor, "business_calendar.holiday.manage", organization_id)
        calendar = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(calendar)
        row = self.repository.holiday(
            organization_id, calendar_id, holiday_id, lock=True
        )
        if row is None:
            raise BusinessCalendarNotFound("holiday not found")
        self._check_version(row.version, payload.expected_version)
        previous = calendar.version
        row.name = payload.name
        row.scope = payload.scope
        row.intervals = _interval_payload(payload.intervals)
        row.version += 1
        row.updated_by_user_id = actor.id
        row.updated_at = self.clock.now()
        calendar.version += 1
        calendar.updated_by_user_id = actor.id
        calendar.updated_at = row.updated_at
        self._audit(
            calendar,
            resource_type="holiday",
            resource_id=row.id,
            action="holiday.updated",
            actor=actor,
            previous_version=previous,
            new_version=calendar.version,
            changes={"scope": row.scope, "interval_count": len(row.intervals)},
            correlation_id=correlation_id or uuid4(),
        )
        response = self._holiday_response(row)
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=None,
            command="holiday.update",
            request_hash="",
            response_type=HolidayResponse,
        )

    def create_override(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        payload: ManualOverrideCreate,
        actor: User,
        *,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> ManualOverrideResponse:
        self._authorize(actor, "business_calendar.override.manage", organization_id)
        key = self._idempotency_key(idempotency_key)
        command = f"override.create:{calendar_id}"
        request_hash = self._request_hash(command, payload.model_dump(mode="json"))
        replay = self._replay(
            organization_id, key, command, request_hash, ManualOverrideResponse
        )
        if replay is not None:
            return replay
        calendar = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(calendar)
        previous = calendar.version
        calendar.version += 1
        now = self.clock.now()
        calendar.updated_by_user_id = actor.id
        calendar.updated_at = now
        row = BusinessCalendarOverrideModel(
            id=uuid4(),
            organization_id=organization_id,
            calendar_id=calendar_id,
            decision=payload.decision,
            starts_at=payload.starts_at.astimezone(UTC),
            ends_at=(
                payload.ends_at.astimezone(UTC) if payload.ends_at is not None else None
            ),
            reason=payload.reason,
            version=calendar.version,
            created_by_user_id=actor.id,
            created_at=now,
        )
        self.repository.add(row)
        response = self._override_response(row)
        self._audit(
            calendar,
            resource_type="override",
            resource_id=row.id,
            action="override.created",
            actor=actor,
            previous_version=previous,
            new_version=calendar.version,
            changes={
                "decision": row.decision,
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat() if row.ends_at else None,
            },
            correlation_id=correlation_id or uuid4(),
        )
        self._receipt(
            organization_id,
            key,
            command,
            request_hash,
            "override",
            row.id,
            response,
        )
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=ManualOverrideResponse,
        )

    def list_overrides(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        actor: User,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ManualOverrideResponse], int]:
        self._authorize(actor, "business_calendar.read", organization_id)
        self._calendar(organization_id, calendar_id)
        self._validate_pagination(offset, limit)
        rows, total = self.repository.overrides(
            organization_id,
            calendar_id,
            starts_before=None,
            ends_after=None,
            offset=offset,
            limit=limit,
        )
        return [self._override_response(row) for row in rows], total

    def revoke_override(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        override_id: UUID,
        payload: ManualOverrideRevoke,
        actor: User,
        *,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> ManualOverrideResponse:
        self._authorize(actor, "business_calendar.override.manage", organization_id)
        key = self._idempotency_key(idempotency_key)
        command = f"override.revoke:{override_id}"
        request_hash = self._request_hash(command, payload.model_dump(mode="json"))
        replay = self._replay(
            organization_id, key, command, request_hash, ManualOverrideResponse
        )
        if replay is not None:
            return replay
        calendar = self._calendar(organization_id, calendar_id, lock=True)
        self._ensure_mutable(calendar)
        row = self.repository.override(
            organization_id, calendar_id, override_id, lock=True
        )
        if row is None:
            raise BusinessCalendarNotFound("manual override not found")
        self._check_version(row.version, payload.expected_version)
        if row.revoked_at is not None:
            raise BusinessCalendarConflict("manual override is already revoked")
        previous = calendar.version
        calendar.version += 1
        now = self.clock.now()
        calendar.updated_by_user_id = actor.id
        calendar.updated_at = now
        row.version = calendar.version
        row.revoked_by_user_id = actor.id
        row.revoked_at = now
        response = self._override_response(row)
        self._audit(
            calendar,
            resource_type="override",
            resource_id=row.id,
            action="override.revoked",
            actor=actor,
            previous_version=previous,
            new_version=calendar.version,
            changes={"revoked": True},
            correlation_id=correlation_id or uuid4(),
        )
        self._receipt(
            organization_id,
            key,
            command,
            request_hash,
            "override",
            row.id,
            response,
        )
        return self._commit_result(
            response,
            organization_id=organization_id,
            key=key,
            command=command,
            request_hash=request_hash,
            response_type=ManualOverrideResponse,
        )

    def resolve(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        evaluated_at: datetime,
        actor: User,
        *,
        correlation_id: UUID | None = None,
    ) -> BusinessHoursResolutionResponse:
        self._authorize(actor, "business_calendar.resolve", organization_id)
        calendar = self._calendar(organization_id, calendar_id)
        return self._resolve_calendar_row(
            organization_id,
            calendar,
            evaluated_at,
            correlation_id=correlation_id,
        )

    def resolve_applicable(
        self,
        organization_id: UUID,
        bot_id: UUID,
        evaluated_at: datetime,
        *,
        correlation_id: UUID | None = None,
    ) -> BusinessHoursResolutionResponse | None:
        """Resolve the active bot-specific calendar, then the organization default."""
        self._validate_bot(organization_id, bot_id)
        calendar = self.repository.active_applicable_calendar(
            organization_id,
            bot_id,
        )
        if calendar is None:
            return None
        return self._resolve_calendar_row(
            organization_id,
            calendar,
            evaluated_at,
            correlation_id=correlation_id,
        )

    def resolve_default(
        self,
        organization_id: UUID,
        evaluated_at: datetime,
        *,
        correlation_id: UUID | None = None,
    ) -> BusinessHoursResolutionResponse | None:
        """Resolve only the active organization-default calendar."""
        calendar = self.repository.active_default_calendar(organization_id)
        if calendar is None:
            return None
        return self._resolve_calendar_row(
            organization_id,
            calendar,
            evaluated_at,
            correlation_id=correlation_id,
        )

    def _resolve_calendar_row(
        self,
        organization_id: UUID,
        calendar: BusinessCalendarModel,
        evaluated_at: datetime,
        *,
        correlation_id: UUID | None = None,
    ) -> BusinessHoursResolutionResponse:
        if evaluated_at.tzinfo is None:
            self.metrics.record_validation_error()
            raise ScheduleValidationError("resolution instant must be timezone-aware")
        if calendar.status != "active":
            raise BusinessCalendarInactive("business calendar is not active")
        calendar_id = calendar.id
        started = perf_counter()
        instant = evaluated_at.astimezone(UTC)
        zone = zone_info(calendar.timezone)
        local_date = instant.astimezone(zone).date()
        date_to = local_date + timedelta(days=8)
        weekly_rows = self.repository.weekly_intervals(organization_id, calendar_id)
        exception_rows, _ = self.repository.date_exceptions(
            organization_id,
            calendar_id,
            date_from=local_date,
            date_to=date_to,
            offset=0,
            limit=1000,
        )
        holiday_rows, _ = self.repository.holidays(
            organization_id,
            calendar_id,
            date_from=local_date,
            date_to=date_to,
            offset=0,
            limit=1000,
        )
        override_rows, _ = self.repository.overrides(
            organization_id,
            calendar_id,
            starts_before=instant + timedelta(days=8),
            ends_after=instant,
            offset=0,
            limit=1000,
        )
        weekly: dict[int, list[CanonicalInterval]] = {}
        for item in weekly_rows:
            weekly.setdefault(item.weekday, []).append(
                CanonicalInterval(item.id, item.start_minute, item.end_minute)
            )
        rules = ResolutionRules(
            weekly={key: tuple(value) for key, value in weekly.items()},
            exceptions=tuple(
                CanonicalDateException(
                    item.id,
                    item.local_date,
                    cast(DateExceptionMode, item.mode),
                    tuple(
                        CanonicalInterval(
                            uuid4(), interval.start_minute, interval.end_minute
                        )
                        for interval in _interval_contracts(item.intervals)
                    ),
                )
                for item in exception_rows
            ),
            holidays=tuple(
                CanonicalHoliday(
                    item.id,
                    item.local_date,
                    cast(HolidayScope, item.scope),
                    tuple(
                        CanonicalInterval(
                            uuid4(), interval.start_minute, interval.end_minute
                        )
                        for interval in _interval_contracts(item.intervals)
                    ),
                )
                for item in holiday_rows
            ),
            overrides=tuple(
                CanonicalOverride(
                    item.id,
                    cast(OverrideDecision, item.decision),
                    _aware(item.starts_at),
                    _aware(item.ends_at) if item.ends_at else None,
                    item.version,
                    _aware(item.created_at),
                    _aware(item.revoked_at) if item.revoked_at else None,
                )
                for item in override_rows
            ),
        )
        result = self.resolver.resolve(
            ResolutionCalendar(calendar.id, calendar.timezone, calendar.version),
            rules,
            instant,
        )
        latency_ms = max(0, int((perf_counter() - started) * 1000))
        self.metrics.record_resolution(result.state, latency_ms)
        self.metrics.set_active_overrides(
            sum(
                1
                for item in override_rows
                if item.revoked_at is None
                and _aware(item.starts_at) <= instant
                and (item.ends_at is None or instant < _aware(item.ends_at))
            )
        )
        self.logger.info(
            "business_calendar_resolved",
            organization_id=str(organization_id),
            calendar_id=str(calendar_id),
            state=result.state,
            winning_rule_type=result.winning_rule_type,
            calendar_version=result.calendar_version,
            latency_ms=latency_ms,
            correlation_id=str(correlation_id or uuid4()),
        )
        return result

    def audit_history(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        actor: User,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[AuditEventResponse], int]:
        self._authorize(actor, "business_calendar.read", organization_id)
        self._calendar(organization_id, calendar_id)
        self._validate_pagination(offset, limit)
        rows, total = self.repository.audit_events(
            organization_id, calendar_id, offset=offset, limit=limit
        )
        return [AuditEventResponse.model_validate(row) for row in rows], total
