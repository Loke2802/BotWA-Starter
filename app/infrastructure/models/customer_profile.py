"""Commercial data; contact identity remains in the encrypted contact record."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class CustomerProfileModel(Base):
    __tablename__ = "customer_profile"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assigned_user_id", "organization_id"],
            ["app_user.id", "app_user.organization_id"],
            name="fk_customer_profile_assignee_tenant",
        ),
        CheckConstraint(
            "service_interest IN ('undecided','luri','site','marketing','other')",
            name="customer_service",
        ),
        ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_customer_profile_contact_tenant",
        ),
        CheckConstraint(
            "classification IN ('lead','customer','inactive')",
            name="customer_classification",
        ),
        CheckConstraint("version > 0", name="customer_version"),
        Index(
            "ix_customer_profile_org_follow_up", "organization_id", "next_follow_up_at"
        ),
    )
    contact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    classification: Mapped[str] = mapped_column(
        String(20), nullable=False, default="lead"
    )
    service_interest: Mapped[str] = mapped_column(
        String(40), nullable=False, default="undecided"
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id")
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
