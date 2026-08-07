from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class ContactModel(Base):
    __tablename__ = "contact"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "channel_type",
            "external_identifier_hash",
            name="uq_contact_organization_channel_identity",
        ),
        CheckConstraint("status IN ('active', 'archived')", name="contact_status"),
        Index("ix_contact_organization_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False, index=True
    )
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    external_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    external_identifier_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_identifier_version: Mapped[int] = mapped_column(
        nullable=False, default=1
    )
    display_name_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=True
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=True
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
