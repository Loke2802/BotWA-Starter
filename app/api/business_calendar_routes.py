from datetime import date, datetime
from typing import Annotated, NoReturn
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.business_calendar_dependencies import get_business_calendar_service
from app.api.dependencies import require_permission
from app.application.business_calendar.service import BusinessCalendarService
from app.domain.business_calendar.contracts import (
    BusinessCalendarCreate,
    BusinessCalendarListResponse,
    BusinessCalendarResponse,
    BusinessCalendarUpdate,
    BusinessHoursResolutionResponse,
    CalendarStatus,
    DateExceptionCreate,
    DateExceptionListResponse,
    DateExceptionResponse,
    DateExceptionUpdate,
    HolidayCreate,
    HolidayListResponse,
    HolidayResponse,
    HolidayUpdate,
    ManualOverrideCreate,
    ManualOverrideListResponse,
    ManualOverrideResponse,
    ManualOverrideRevoke,
    WeeklyScheduleReplace,
    WeeklyScheduleResponse,
)
from app.domain.business_calendar.errors import (
    BusinessCalendarConflict,
    BusinessCalendarError,
    BusinessCalendarForbidden,
    BusinessCalendarNotFound,
    BusinessCalendarPersistenceError,
    ExternalCalendarUnavailable,
    ScheduleValidationError,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/business-calendars",
    tags=["business-calendars"],
)

IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
CorrelationHeader = Annotated[UUID | None, Header(alias="X-Correlation-ID")]
StatusFilter = Annotated[CalendarStatus | None, Query(alias="status")]


def _correlation(value: UUID | None) -> UUID:
    return value or uuid4()


def _raise(exc: BusinessCalendarError) -> NoReturn:
    if isinstance(exc, BusinessCalendarNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, BusinessCalendarForbidden):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, BusinessCalendarConflict):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, ScheduleValidationError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, BusinessCalendarPersistenceError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, ExternalCalendarUnavailable):
        code = status.HTTP_502_BAD_GATEWAY
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=code, detail={"code": exc.safe_code}) from exc


@router.post(
    "",
    response_model=BusinessCalendarResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_calendar(
    organization_id: UUID,
    payload: BusinessCalendarCreate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.create"))],
    idempotency_key: IdempotencyHeader = None,
    correlation_id: CorrelationHeader = None,
) -> BusinessCalendarResponse:
    try:
        return service.create_calendar(
            organization_id,
            payload,
            actor,
            idempotency_key=idempotency_key,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("", response_model=BusinessCalendarListResponse)
def list_calendars(
    organization_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.read"))],
    status_filter: StatusFilter = None,
    bot_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> BusinessCalendarListResponse:
    try:
        items, total = service.list_calendars(
            organization_id,
            actor,
            status=status_filter,
            bot_id=bot_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return BusinessCalendarListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("/{calendar_id}", response_model=BusinessCalendarResponse)
def get_calendar(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.read"))],
) -> BusinessCalendarResponse:
    try:
        return service.get_calendar(organization_id, calendar_id, actor)
    except BusinessCalendarError as exc:
        _raise(exc)


@router.patch("/{calendar_id}", response_model=BusinessCalendarResponse)
def update_calendar(
    organization_id: UUID,
    calendar_id: UUID,
    payload: BusinessCalendarUpdate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.update"))],
    correlation_id: CorrelationHeader = None,
) -> BusinessCalendarResponse:
    try:
        return service.update_calendar(
            organization_id,
            calendar_id,
            payload,
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post("/{calendar_id}/activate", response_model=BusinessCalendarResponse)
def activate_calendar(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.activate"))],
    correlation_id: CorrelationHeader = None,
) -> BusinessCalendarResponse:
    try:
        return service.transition_calendar(
            organization_id,
            calendar_id,
            "activate",
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post("/{calendar_id}/deactivate", response_model=BusinessCalendarResponse)
def deactivate_calendar(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.deactivate"))],
    correlation_id: CorrelationHeader = None,
) -> BusinessCalendarResponse:
    try:
        return service.transition_calendar(
            organization_id,
            calendar_id,
            "deactivate",
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post("/{calendar_id}/archive", response_model=BusinessCalendarResponse)
def archive_calendar(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.archive"))],
    correlation_id: CorrelationHeader = None,
) -> BusinessCalendarResponse:
    try:
        return service.transition_calendar(
            organization_id,
            calendar_id,
            "archive",
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("/{calendar_id}/weekly-schedule", response_model=WeeklyScheduleResponse)
def get_weekly_schedule(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.read"))],
) -> WeeklyScheduleResponse:
    try:
        return service.get_weekly_schedule(organization_id, calendar_id, actor)
    except BusinessCalendarError as exc:
        _raise(exc)


@router.put("/{calendar_id}/weekly-schedule", response_model=WeeklyScheduleResponse)
def replace_weekly_schedule(
    organization_id: UUID,
    calendar_id: UUID,
    payload: WeeklyScheduleReplace,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.schedule.manage"))
    ],
    idempotency_key: IdempotencyHeader = None,
    correlation_id: CorrelationHeader = None,
) -> WeeklyScheduleResponse:
    try:
        return service.replace_weekly_schedule(
            organization_id,
            calendar_id,
            payload,
            actor,
            idempotency_key=idempotency_key,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post(
    "/{calendar_id}/date-exceptions",
    response_model=DateExceptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_date_exception(
    organization_id: UUID,
    calendar_id: UUID,
    payload: DateExceptionCreate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.exception.manage"))
    ],
    idempotency_key: IdempotencyHeader = None,
    correlation_id: CorrelationHeader = None,
) -> DateExceptionResponse:
    try:
        return service.create_date_exception(
            organization_id,
            calendar_id,
            payload,
            actor,
            idempotency_key=idempotency_key,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("/{calendar_id}/date-exceptions", response_model=DateExceptionListResponse)
def list_date_exceptions(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.read"))],
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DateExceptionListResponse:
    try:
        items, total = service.list_date_exceptions(
            organization_id,
            calendar_id,
            actor,
            date_from=date_from,
            date_to=date_to,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return DateExceptionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.patch(
    "/{calendar_id}/date-exceptions/{exception_id}",
    response_model=DateExceptionResponse,
)
def update_date_exception(
    organization_id: UUID,
    calendar_id: UUID,
    exception_id: UUID,
    payload: DateExceptionUpdate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.exception.manage"))
    ],
    correlation_id: CorrelationHeader = None,
) -> DateExceptionResponse:
    try:
        return service.update_date_exception(
            organization_id,
            calendar_id,
            exception_id,
            payload,
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post(
    "/{calendar_id}/holidays",
    response_model=HolidayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_holiday(
    organization_id: UUID,
    calendar_id: UUID,
    payload: HolidayCreate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.holiday.manage"))
    ],
    idempotency_key: IdempotencyHeader = None,
    correlation_id: CorrelationHeader = None,
) -> HolidayResponse:
    try:
        return service.create_holiday(
            organization_id,
            calendar_id,
            payload,
            actor,
            idempotency_key=idempotency_key,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("/{calendar_id}/holidays", response_model=HolidayListResponse)
def list_holidays(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.read"))],
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> HolidayListResponse:
    try:
        items, total = service.list_holidays(
            organization_id,
            calendar_id,
            actor,
            date_from=date_from,
            date_to=date_to,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return HolidayListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.patch("/{calendar_id}/holidays/{holiday_id}", response_model=HolidayResponse)
def update_holiday(
    organization_id: UUID,
    calendar_id: UUID,
    holiday_id: UUID,
    payload: HolidayUpdate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.holiday.manage"))
    ],
    correlation_id: CorrelationHeader = None,
) -> HolidayResponse:
    try:
        return service.update_holiday(
            organization_id,
            calendar_id,
            holiday_id,
            payload,
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post(
    "/{calendar_id}/overrides",
    response_model=ManualOverrideResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_override(
    organization_id: UUID,
    calendar_id: UUID,
    payload: ManualOverrideCreate,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.override.manage"))
    ],
    idempotency_key: IdempotencyHeader = None,
    correlation_id: CorrelationHeader = None,
) -> ManualOverrideResponse:
    try:
        return service.create_override(
            organization_id,
            calendar_id,
            payload,
            actor,
            idempotency_key=idempotency_key,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("/{calendar_id}/overrides", response_model=ManualOverrideListResponse)
def list_overrides(
    organization_id: UUID,
    calendar_id: UUID,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ManualOverrideListResponse:
    try:
        items, total = service.list_overrides(
            organization_id,
            calendar_id,
            actor,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return ManualOverrideListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.post(
    "/{calendar_id}/overrides/{override_id}/revoke",
    response_model=ManualOverrideResponse,
)
def revoke_override(
    organization_id: UUID,
    calendar_id: UUID,
    override_id: UUID,
    payload: ManualOverrideRevoke,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[
        User, Depends(require_permission("business_calendar.override.manage"))
    ],
    idempotency_key: IdempotencyHeader = None,
    correlation_id: CorrelationHeader = None,
) -> ManualOverrideResponse:
    try:
        return service.revoke_override(
            organization_id,
            calendar_id,
            override_id,
            payload,
            actor,
            idempotency_key=idempotency_key,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)


@router.get("/{calendar_id}/resolve", response_model=BusinessHoursResolutionResponse)
def resolve_calendar(
    organization_id: UUID,
    calendar_id: UUID,
    at: datetime,
    service: Annotated[BusinessCalendarService, Depends(get_business_calendar_service)],
    actor: Annotated[User, Depends(require_permission("business_calendar.resolve"))],
    correlation_id: CorrelationHeader = None,
) -> BusinessHoursResolutionResponse:
    try:
        return service.resolve(
            organization_id,
            calendar_id,
            at,
            actor,
            correlation_id=_correlation(correlation_id),
        )
    except BusinessCalendarError as exc:
        _raise(exc)
