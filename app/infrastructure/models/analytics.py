from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class ConversationManagementEventModel(Base):
    __tablename__ = "conversation_management_event"
    __table_args__ = (
        CheckConstraint(
            "from_status IN ('open','closed','archived')",
            name="conversation_management_event_from_status",
        ),
        CheckConstraint(
            "to_status IN ('open','closed','archived')",
            name="conversation_management_event_to_status",
        ),
        CheckConstraint(
            "actor_type IN ('user','system','automation')",
            name="conversation_management_event_actor_type",
        ),
        Index(
            "ix_conversation_management_event_org_occurred",
            "organization_id",
            "occurred_at",
        ),
        Index(
            "ix_conversation_management_event_org_bot_occurred",
            "organization_id",
            "bot_id",
            "occurred_at",
        ),
        Index(
            "ix_conversation_management_event_conversation_occurred",
            "conversation_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation.id"), nullable=False
    )
    bot_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("bot.id"), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class HandoffCycleModel(Base):
    __tablename__ = "handoff_cycle"
    __table_args__ = (
        CheckConstraint(
            "resolution_type IS NULL OR "
            "resolution_type IN ('resolved','returned_to_bot')",
            name="handoff_cycle_resolution_type",
        ),
        CheckConstraint(
            "activated_at IS NULL OR activated_at >= requested_at",
            name="handoff_cycle_activated_after_request",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= requested_at",
            name="handoff_cycle_resolved_after_request",
        ),
        Index("ix_handoff_cycle_org_requested", "organization_id", "requested_at"),
        Index(
            "ix_handoff_cycle_org_bot_requested",
            "organization_id",
            "bot_id",
            "requested_at",
        ),
        Index("ix_handoff_cycle_org_resolved", "organization_id", "resolved_at"),
        Index(
            "uq_handoff_cycle_open_session",
            "handoff_session_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
            sqlite_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation.id"), nullable=False
    )
    bot_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("bot.id"), nullable=False)
    handoff_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("handoff_session.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_type: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AnalyticsDailySummaryModel(Base):
    __tablename__ = "analytics_daily_summary"
    __table_args__ = (
        CheckConstraint(
            "conversations_started >= 0 AND conversations_closed >= 0 AND "
            "handoffs_created >= 0 AND handoffs_resolved >= 0 AND "
            "handoff_resolution_seconds_sum >= 0 AND handoff_resolution_count >= 0 "
            "AND automation_executions_created >= 0 AND automation_succeeded >= 0 "
            "AND automation_failed >= 0 AND automation_skipped >= 0 "
            "AND automation_cancelled >= 0 AND contacts_created >= 0",
            name="analytics_daily_summary_nonnegative",
        ),
        Index(
            "uq_analytics_daily_summary_bot",
            "organization_id",
            "bot_id",
            "local_date",
            unique=True,
            postgresql_where=text("bot_id IS NOT NULL"),
            sqlite_where=text("bot_id IS NOT NULL"),
        ),
        Index(
            "uq_analytics_daily_summary_organization",
            "organization_id",
            "local_date",
            unique=True,
            postgresql_where=text("bot_id IS NULL"),
            sqlite_where=text("bot_id IS NULL"),
        ),
        Index("ix_analytics_daily_summary_org_date", "organization_id", "local_date"),
        Index(
            "ix_analytics_daily_summary_org_bot_date",
            "organization_id",
            "bot_id",
            "local_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    bot_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("bot.id"))
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    conversations_started: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    conversations_closed: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    handoffs_created: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    handoffs_resolved: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    handoff_resolution_seconds_sum: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    handoff_resolution_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    automation_executions_created: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    automation_succeeded: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    automation_failed: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    automation_skipped: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    automation_cancelled: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    contacts_created: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source_watermark_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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
