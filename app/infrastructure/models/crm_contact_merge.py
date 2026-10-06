"""Durable identity redirects; originals and encrypted review snapshots survive."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base
from app.infrastructure.models.crm_opportunity import now


class ContactMergeModel(Base):
    __tablename__ = "crm_contact_merge"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_merge_source",
        ),
        ForeignKeyConstraint(
            ["target_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_merge_target",
        ),
        CheckConstraint("source_id <> target_id", name="crm_merge_distinct"),
    )
    source_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    target_id: Mapped[UUID] = mapped_column(Uuid)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id"))
    snapshot_ciphertext: Mapped[str] = mapped_column(Text)
    review_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
