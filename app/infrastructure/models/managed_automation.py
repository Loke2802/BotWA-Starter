from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class ManagedAutomationDefinitionModel(Base):
    __tablename__ = "managed_automation_definition"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="managed_automation_definition_status",
        ),
        CheckConstraint(
            "trigger_type = 'conversation.inbound_received'",
            name="managed_automation_definition_trigger",
        ),
        CheckConstraint(
            "action_type = 'request_handoff'",
            name="managed_automation_definition_action",
        ),
        Index(
            "ix_managed_automation_definition_org_status", "organization_id", "status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False, index=True
    )
    bot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("bot.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False)
    conditions_data: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action_data: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
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


class ManagedAutomationEventReceiptModel(Base):
    __tablename__ = "managed_automation_event_receipt"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_type",
            "source_event_id",
            name="uq_managed_automation_event_source",
        ),
        Index("ix_managed_automation_event_org_type", "organization_id", "event_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False, index=True
    )
    bot_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("bot.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    causation_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_automation_id: Mapped[UUID | None] = mapped_column(Uuid)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ManagedAutomationExecutionModel(Base):
    __tablename__ = "managed_automation_execution"
    __table_args__ = (
        UniqueConstraint(
            "automation_definition_id",
            "definition_version",
            "event_receipt_id",
            name="uq_managed_automation_execution_event",
        ),
        CheckConstraint(
            "status IN "
            "('pending','running','succeeded','failed','skipped','cancelled')",
            name="managed_automation_execution_status",
        ),
        Index("ix_managed_automation_execution_claim", "status", "available_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False, index=True
    )
    automation_definition_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("managed_automation_definition.id"), nullable=False, index=True
    )
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_receipt_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("managed_automation_event_receipt.id"), nullable=False
    )
    definition_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    event_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_error_code: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    causation_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
