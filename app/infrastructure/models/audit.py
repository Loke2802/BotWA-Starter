from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class AuditEventModel(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user','system','automation')",
            name="audit_event_actor_type",
        ),
        CheckConstraint("result = 'success'", name="audit_event_result"),
        CheckConstraint(
            "(actor_type = 'user' AND actor_user_id IS NOT NULL "
            "AND actor_role IS NOT NULL) OR (actor_type IN "
            "('system','automation') AND actor_user_id IS NULL "
            "AND actor_role IS NULL)",
            name="audit_event_actor_shape",
        ),
        Index(
            "ix_audit_event_org_occurred_id",
            "organization_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_audit_event_org_action_occurred",
            "organization_id",
            "action",
            "occurred_at",
        ),
        Index(
            "ix_audit_event_org_actor_occurred",
            "organization_id",
            "actor_user_id",
            "occurred_at",
        ),
        Index(
            "ix_audit_event_org_resource_occurred",
            "organization_id",
            "resource_type",
            "resource_id",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    metadata_data: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
