"""Tenant constraints and durable commercial records; PII is encrypted."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


def now() -> datetime:
    return datetime.now(UTC)


class CrmStageModel(Base):
    __tablename__ = "crm_stage"
    __table_args__ = (
        CheckConstraint("kind IN ('open','won','lost')", name="crm_stage_kind"),
        CheckConstraint("position >= 0", name="crm_stage_position"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(10))
    position: Mapped[int] = mapped_column(Integer)


class OpportunityModel(Base):
    __tablename__ = "crm_opportunity"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_crm_opportunity_tenant"),
        UniqueConstraint(
            "id", "organization_id", "contact_id", name="uq_crm_opportunity_contact"
        ),
        UniqueConstraint(
            "organization_id",
            "created_by_user_id",
            "idempotency_key",
            name="uq_crm_opportunity_idempotency",
        ),
        ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_opportunity_contact",
        ),
        ForeignKeyConstraint(
            ["assigned_user_id", "organization_id"],
            ["app_user.id", "app_user.organization_id"],
            name="fk_crm_opportunity_assignee",
        ),
        ForeignKeyConstraint(
            ["stage_code", "organization_id"],
            ["crm_stage.code", "crm_stage.organization_id"],
            name="fk_crm_opportunity_stage",
        ),
        CheckConstraint("version > 0", name="crm_opportunity_version"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="crm_opportunity_amount"),
        CheckConstraint(
            "(amount IS NULL AND currency IS NULL) OR "
            "(amount IS NOT NULL AND currency IS NOT NULL)",
            name="crm_opportunity_currency",
        ),
        Index("ix_crm_opportunity_contact", "organization_id", "contact_id"),
        Index(
            "ix_crm_opportunity_stage",
            "organization_id",
            "stage_code",
            "assigned_user_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organization.id"))
    contact_id: Mapped[UUID] = mapped_column(Uuid)
    title_ciphertext: Mapped[str] = mapped_column(Text)
    need_ciphertext: Mapped[str | None] = mapped_column(Text)
    stage_code: Mapped[str] = mapped_column(String(40))
    assigned_user_id: Mapped[UUID] = mapped_column(Uuid)
    no_action_reason_ciphertext: Mapped[str | None] = mapped_column(Text)
    close_reason_ciphertext: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpportunityConversationModel(Base):
    __tablename__ = "crm_opportunity_conversation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["opportunity_id", "organization_id", "contact_id"],
            [
                "crm_opportunity.id",
                "crm_opportunity.organization_id",
                "crm_opportunity.contact_id",
            ],
            name="fk_crm_link_opportunity",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "organization_id", "contact_id"],
            [
                "conversation.id",
                "conversation.organization_id",
                "conversation.contact_id",
            ],
            name="fk_crm_link_conversation",
        ),
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    contact_id: Mapped[UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OpportunityActivityModel(Base):
    __tablename__ = "crm_activity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["opportunity_id", "organization_id"],
            ["crm_opportunity.id", "crm_opportunity.organization_id"],
            name="fk_crm_activity_opportunity",
        ),
        ForeignKeyConstraint(
            ["assigned_user_id", "organization_id"],
            ["app_user.id", "app_user.organization_id"],
            name="fk_crm_activity_assignee",
        ),
        UniqueConstraint("opportunity_id", "version", name="uq_crm_activity_version"),
        CheckConstraint(
            "status IN ('pending','completed','cancelled')", name="crm_activity_status"
        ),
        CheckConstraint("version > 0", name="crm_activity_version"),
        Index("ix_crm_activity_due", "organization_id", "status", "due_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    assigned_user_id: Mapped[UUID] = mapped_column(Uuid)
    description_ciphertext: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpportunityHistoryModel(Base):
    __tablename__ = "crm_opportunity_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["opportunity_id", "organization_id"],
            ["crm_opportunity.id", "crm_opportunity.organization_id"],
            name="fk_crm_history_opportunity",
        ),
        CheckConstraint("version > 0", name="crm_history_version"),
    )
    opportunity_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    snapshot_ciphertext: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
