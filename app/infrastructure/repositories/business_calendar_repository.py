from datetime import date, datetime
from uuid import UUID

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session

from app.domain.business_calendar.contracts import CalendarStatus
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_calendar import (
    BusinessCalendarAuditEventModel,
    BusinessCalendarDateExceptionModel,
    BusinessCalendarHolidayModel,
    BusinessCalendarIdempotencyReceiptModel,
    BusinessCalendarModel,
    BusinessCalendarOverrideModel,
    BusinessCalendarWeeklyIntervalModel,
)


class BusinessCalendarRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, row: object) -> None:
        self.session.add(row)

    def bot_belongs_to(self, organization_id: UUID, bot_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(BotModel.id).where(
                    BotModel.organization_id == organization_id,
                    BotModel.id == bot_id,
                )
            )
            is not None
        )

    def calendar(
        self, organization_id: UUID, calendar_id: UUID, *, lock: bool = False
    ) -> BusinessCalendarModel | None:
        stmt = select(BusinessCalendarModel).where(
            BusinessCalendarModel.organization_id == organization_id,
            BusinessCalendarModel.id == calendar_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def calendars(
        self,
        organization_id: UUID,
        *,
        status: CalendarStatus | None,
        bot_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[BusinessCalendarModel], int]:
        filters = [BusinessCalendarModel.organization_id == organization_id]
        if status is not None:
            filters.append(BusinessCalendarModel.status == status)
        if bot_id is not None:
            filters.append(BusinessCalendarModel.bot_id == bot_id)
        query = (
            select(BusinessCalendarModel)
            .where(*filters)
            .order_by(BusinessCalendarModel.created_at.desc(), BusinessCalendarModel.id)
            .offset(offset)
            .limit(limit)
        )
        total = select(func.count()).select_from(BusinessCalendarModel).where(*filters)
        return list(self.session.scalars(query)), int(self.session.scalar(total) or 0)

    def active_applicable_calendar(
        self,
        organization_id: UUID,
        bot_id: UUID,
    ) -> BusinessCalendarModel | None:
        stmt = (
            select(BusinessCalendarModel)
            .where(
                BusinessCalendarModel.organization_id == organization_id,
                BusinessCalendarModel.status == "active",
                or_(
                    BusinessCalendarModel.bot_id == bot_id,
                    BusinessCalendarModel.bot_id.is_(None),
                ),
            )
            .order_by(
                case((BusinessCalendarModel.bot_id == bot_id, 0), else_=1),
                BusinessCalendarModel.id,
            )
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def active_default_calendar(
        self, organization_id: UUID
    ) -> BusinessCalendarModel | None:
        stmt = select(BusinessCalendarModel).where(
            BusinessCalendarModel.organization_id == organization_id,
            BusinessCalendarModel.status == "active",
            BusinessCalendarModel.bot_id.is_(None),
        )
        return self.session.scalars(stmt).one_or_none()

    def weekly_intervals(
        self, organization_id: UUID, calendar_id: UUID
    ) -> list[BusinessCalendarWeeklyIntervalModel]:
        stmt = (
            select(BusinessCalendarWeeklyIntervalModel)
            .where(
                BusinessCalendarWeeklyIntervalModel.organization_id == organization_id,
                BusinessCalendarWeeklyIntervalModel.calendar_id == calendar_id,
            )
            .order_by(
                BusinessCalendarWeeklyIntervalModel.weekday,
                BusinessCalendarWeeklyIntervalModel.start_minute,
                BusinessCalendarWeeklyIntervalModel.id,
            )
        )
        return list(self.session.scalars(stmt))

    def replace_weekly_intervals(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        rows: list[BusinessCalendarWeeklyIntervalModel],
    ) -> None:
        self.session.execute(
            delete(BusinessCalendarWeeklyIntervalModel).where(
                BusinessCalendarWeeklyIntervalModel.organization_id == organization_id,
                BusinessCalendarWeeklyIntervalModel.calendar_id == calendar_id,
            )
        )
        self.session.add_all(rows)

    def date_exception(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        exception_id: UUID,
        *,
        lock: bool = False,
    ) -> BusinessCalendarDateExceptionModel | None:
        stmt = select(BusinessCalendarDateExceptionModel).where(
            BusinessCalendarDateExceptionModel.organization_id == organization_id,
            BusinessCalendarDateExceptionModel.calendar_id == calendar_id,
            BusinessCalendarDateExceptionModel.id == exception_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def date_exceptions(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        *,
        date_from: date | None,
        date_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[BusinessCalendarDateExceptionModel], int]:
        filters = [
            BusinessCalendarDateExceptionModel.organization_id == organization_id,
            BusinessCalendarDateExceptionModel.calendar_id == calendar_id,
        ]
        if date_from is not None:
            filters.append(BusinessCalendarDateExceptionModel.local_date >= date_from)
        if date_to is not None:
            filters.append(BusinessCalendarDateExceptionModel.local_date <= date_to)
        query = (
            select(BusinessCalendarDateExceptionModel)
            .where(*filters)
            .order_by(BusinessCalendarDateExceptionModel.local_date)
            .offset(offset)
            .limit(limit)
        )
        total = (
            select(func.count())
            .select_from(BusinessCalendarDateExceptionModel)
            .where(*filters)
        )
        return list(self.session.scalars(query)), int(self.session.scalar(total) or 0)

    def holiday(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        holiday_id: UUID,
        *,
        lock: bool = False,
    ) -> BusinessCalendarHolidayModel | None:
        stmt = select(BusinessCalendarHolidayModel).where(
            BusinessCalendarHolidayModel.organization_id == organization_id,
            BusinessCalendarHolidayModel.calendar_id == calendar_id,
            BusinessCalendarHolidayModel.id == holiday_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def holidays(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        *,
        date_from: date | None,
        date_to: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[BusinessCalendarHolidayModel], int]:
        filters = [
            BusinessCalendarHolidayModel.organization_id == organization_id,
            BusinessCalendarHolidayModel.calendar_id == calendar_id,
        ]
        if date_from is not None:
            filters.append(BusinessCalendarHolidayModel.local_date >= date_from)
        if date_to is not None:
            filters.append(BusinessCalendarHolidayModel.local_date <= date_to)
        query = (
            select(BusinessCalendarHolidayModel)
            .where(*filters)
            .order_by(
                BusinessCalendarHolidayModel.local_date, BusinessCalendarHolidayModel.id
            )
            .offset(offset)
            .limit(limit)
        )
        total = (
            select(func.count())
            .select_from(BusinessCalendarHolidayModel)
            .where(*filters)
        )
        return list(self.session.scalars(query)), int(self.session.scalar(total) or 0)

    def override(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        override_id: UUID,
        *,
        lock: bool = False,
    ) -> BusinessCalendarOverrideModel | None:
        stmt = select(BusinessCalendarOverrideModel).where(
            BusinessCalendarOverrideModel.organization_id == organization_id,
            BusinessCalendarOverrideModel.calendar_id == calendar_id,
            BusinessCalendarOverrideModel.id == override_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def overrides(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        *,
        starts_before: datetime | None,
        ends_after: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[BusinessCalendarOverrideModel], int]:
        filters = [
            BusinessCalendarOverrideModel.organization_id == organization_id,
            BusinessCalendarOverrideModel.calendar_id == calendar_id,
        ]
        if starts_before is not None:
            filters.append(BusinessCalendarOverrideModel.starts_at <= starts_before)
        if ends_after is not None:
            filters.append(
                or_(
                    BusinessCalendarOverrideModel.ends_at.is_(None),
                    BusinessCalendarOverrideModel.ends_at > ends_after,
                )
            )
        query = (
            select(BusinessCalendarOverrideModel)
            .where(*filters)
            .order_by(
                BusinessCalendarOverrideModel.version.desc(),
                BusinessCalendarOverrideModel.created_at.desc(),
                BusinessCalendarOverrideModel.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        total = (
            select(func.count())
            .select_from(BusinessCalendarOverrideModel)
            .where(*filters)
        )
        return list(self.session.scalars(query)), int(self.session.scalar(total) or 0)

    def idempotency_receipt(
        self, organization_id: UUID, key: str, *, lock: bool = False
    ) -> BusinessCalendarIdempotencyReceiptModel | None:
        stmt = select(BusinessCalendarIdempotencyReceiptModel).where(
            BusinessCalendarIdempotencyReceiptModel.organization_id == organization_id,
            BusinessCalendarIdempotencyReceiptModel.idempotency_key == key,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def audit_events(
        self,
        organization_id: UUID,
        calendar_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[BusinessCalendarAuditEventModel], int]:
        filters = (
            BusinessCalendarAuditEventModel.organization_id == organization_id,
            BusinessCalendarAuditEventModel.calendar_id == calendar_id,
        )
        query = (
            select(BusinessCalendarAuditEventModel)
            .where(*filters)
            .order_by(
                BusinessCalendarAuditEventModel.created_at.desc(),
                BusinessCalendarAuditEventModel.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        total = (
            select(func.count())
            .select_from(BusinessCalendarAuditEventModel)
            .where(*filters)
        )
        return list(self.session.scalars(query)), int(self.session.scalar(total) or 0)
