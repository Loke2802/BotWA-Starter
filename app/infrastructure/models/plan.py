from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class PlanDefinitionModel(Base):
    __tablename__ = "plan_definition"
    __table_args__ = (
        CheckConstraint("status IN ('active','retired')", name="ck_plan_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class OrganizationPlanAssignmentModel(Base):
    __tablename__ = "organization_plan_assignment"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_plan_assignment_version_positive"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), primary_key=True
    )
    plan_definition_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plan_definition.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
