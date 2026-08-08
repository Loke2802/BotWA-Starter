from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class BusinessCalendarModel(Base):
    __tablename__ = "business_calendar"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="business_calendar_status",
        ),
        CheckConstraint("version > 0", name="business_calendar_version_positive"),
        UniqueConstraint("organization_id", "id", name="uq_business_calendar_org_id"),
        UniqueConstraint(
            "organization_id", "name", name="uq_business_calendar_org_name"
        ),
        Index(
            "ix_business_calendar_org_status",
            "organization_id",
            "status",
            "created_at",
        ),
        Index("ix_business_calendar_org_bot", "organization_id", "bot_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    bot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("bot.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BusinessCalendarWeeklyIntervalModel(Base):
    __tablename__ = "business_calendar_weekly_interval"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "calendar_id"],
            ["business_calendar.organization_id", "business_calendar.id"],
            name="fk_business_weekly_interval_org_calendar",
        ),
        CheckConstraint(
            "weekday BETWEEN 1 AND 7", name="business_weekly_interval_weekday"
        ),
        CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name="business_weekly_interval_start",
        ),
        CheckConstraint(
            "end_minute > 0 AND end_minute <= 1440",
            name="business_weekly_interval_end",
        ),
        CheckConstraint(
            "start_minute < end_minute", name="business_weekly_interval_order"
        ),
        UniqueConstraint(
            "calendar_id",
            "weekday",
            "start_minute",
            "end_minute",
            name="uq_business_weekly_interval",
        ),
        Index(
            "ix_business_weekly_interval_org_calendar_day",
            "organization_id",
            "calendar_id",
            "weekday",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    calendar_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class BusinessCalendarDateExceptionModel(Base):
    __tablename__ = "business_calendar_date_exception"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "calendar_id"],
            ["business_calendar.organization_id", "business_calendar.id"],
            name="fk_business_date_exception_org_calendar",
        ),
        CheckConstraint(
            "mode IN "
            "('closed_all_day','open_all_day','replace','add_open','close_partial')",
            name="business_date_exception_mode",
        ),
        CheckConstraint("version > 0", name="business_date_exception_version_positive"),
        UniqueConstraint(
            "calendar_id", "local_date", name="uq_business_date_exception_date"
        ),
        Index(
            "ix_business_date_exception_org_calendar_date",
            "organization_id",
            "calendar_id",
            "local_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    calendar_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    intervals: Mapped[list[dict[str, int]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class BusinessCalendarHolidayModel(Base):
    __tablename__ = "business_calendar_holiday"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "calendar_id"],
            ["business_calendar.organization_id", "business_calendar.id"],
            name="fk_business_holiday_org_calendar",
        ),
        CheckConstraint(
            "scope IN ('full_day', 'partial')", name="business_holiday_scope"
        ),
        CheckConstraint(
            "source IN ('manual', 'external_import')",
            name="business_holiday_source",
        ),
        CheckConstraint("version > 0", name="business_holiday_version_positive"),
        UniqueConstraint(
            "calendar_id",
            "local_date",
            "name",
            name="uq_business_holiday_date_name",
        ),
        Index(
            "ix_business_holiday_org_calendar_date",
            "organization_id",
            "calendar_id",
            "local_date",
        ),
        Index(
            "ix_business_holiday_external_hash",
            "organization_id",
            "external_reference_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    calendar_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    intervals: Mapped[list[dict[str, int]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    external_reference_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    updated_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class BusinessCalendarOverrideModel(Base):
    __tablename__ = "business_calendar_override"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "calendar_id"],
            ["business_calendar.organization_id", "business_calendar.id"],
            name="fk_business_override_org_calendar",
        ),
        CheckConstraint(
            "decision IN ('open', 'closed')", name="business_override_decision"
        ),
        CheckConstraint("version > 0", name="business_override_version_positive"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at < ends_at",
            name="business_override_window",
        ),
        Index(
            "ix_business_override_org_calendar_window",
            "organization_id",
            "calendar_id",
            "starts_at",
            "ends_at",
        ),
        Index(
            "ix_business_override_active",
            "calendar_id",
            "revoked_at",
            "starts_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    calendar_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BusinessCalendarIdempotencyReceiptModel(Base):
    __tablename__ = "business_calendar_idempotency_receipt"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_business_calendar_idempotency_org_key",
        ),
        Index(
            "ix_business_calendar_idempotency_resource",
            "organization_id",
            "resource_type",
            "resource_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    response_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class BusinessCalendarAuditEventModel(Base):
    __tablename__ = "business_calendar_audit_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "calendar_id"],
            ["business_calendar.organization_id", "business_calendar.id"],
            name="fk_business_audit_org_calendar",
        ),
        Index(
            "ix_business_audit_org_calendar_created",
            "organization_id",
            "calendar_id",
            "created_at",
        ),
        Index("ix_business_audit_correlation", "correlation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    calendar_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    previous_version: Mapped[int | None] = mapped_column(Integer)
    new_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
