from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class OrganizationOnboardingModel(Base):
    __tablename__ = "organization_onboarding"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress','completed')",
            name="organization_onboarding_status",
        ),
        CheckConstraint(
            "version > 0",
            name="organization_onboarding_version_positive",
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL) OR "
            "(status = 'in_progress' AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL)",
            name="organization_onboarding_completion_shape",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="organization_onboarding_completion_order",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
