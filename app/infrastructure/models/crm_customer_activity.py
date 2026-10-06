"""Append-only encrypted customer activity, with tenant and contact constraints."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base
from app.infrastructure.models.crm_opportunity import now


class CrmCustomerActivityModel(Base):
    __tablename__ = "crm_customer_activity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_journal_contact",
        ),
        ForeignKeyConstraint(
            ["opportunity_id", "organization_id", "contact_id"],
            [
                "crm_opportunity.id",
                "crm_opportunity.organization_id",
                "crm_opportunity.contact_id",
            ],
            name="fk_crm_journal_opportunity",
        ),
        ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name="fk_crm_journal_actor",
        ),
        UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_crm_journal_key",
        ),
        CheckConstraint("kind IN ('call','meeting','note')", name="crm_journal_kind"),
        Index(
            "ix_crm_journal_customer", "organization_id", "contact_id", "occurred_at"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    contact_id: Mapped[UUID] = mapped_column(Uuid)
    opportunity_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(10))
    description_ciphertext: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64))
