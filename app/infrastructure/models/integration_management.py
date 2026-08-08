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


class IntegrationConnectionModel(Base):
    __tablename__ = "integration_connection"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="integration_connection_status",
        ),
        CheckConstraint(
            "integration_type IN ('calendar', 'crm', 'erp', 'custom_api')",
            name="integration_connection_type",
        ),
        CheckConstraint(
            "provider IN ('google_calendar')",
            name="integration_connection_provider",
        ),
        CheckConstraint(
            "health_status IN "
            "('unknown', 'healthy', 'degraded', 'unreachable', 'auth_error')",
            name="integration_connection_health_status",
        ),
        UniqueConstraint(
            "organization_id", "name", name="uq_integration_connection_org_name"
        ),
        Index(
            "ix_integration_connection_org_status",
            "organization_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_integration_connection_org_provider_status",
            "organization_id",
            "provider",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    bot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("bot.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    integration_type: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    health_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    last_health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
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


class IntegrationCredentialModel(Base):
    __tablename__ = "integration_credential"
    __table_args__ = (
        CheckConstraint(
            "credential_type = 'google_oauth_refresh'",
            name="integration_credential_type",
        ),
        UniqueConstraint(
            "integration_connection_id",
            name="uq_integration_credential_connection",
        ),
        Index(
            "ix_integration_credential_org_connection",
            "organization_id",
            "integration_connection_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    integration_connection_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("integration_connection.id"), nullable=False
    )
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(30), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationHealthCheckModel(Base):
    __tablename__ = "integration_health_check"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('unknown', 'healthy', 'degraded', 'unreachable', 'auth_error')",
            name="integration_health_check_status",
        ),
        CheckConstraint(
            "safe_error_code IS NULL OR safe_error_code IN "
            "('INTEGRATION_AUTH_REQUIRED','INTEGRATION_AUTH_FAILED',"
            "'INTEGRATION_UNREACHABLE','INTEGRATION_PROVIDER_ERROR',"
            "'INTEGRATION_CONFIGURATION_INVALID','INTEGRATION_NOT_ACTIVE',"
            "'INTEGRATION_CREDENTIAL_INVALID')",
            name="integration_health_check_safe_error",
        ),
        Index(
            "ix_integration_health_connection_checked",
            "integration_connection_id",
            "checked_at",
        ),
        Index("ix_integration_health_org_checked", "organization_id", "checked_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    integration_connection_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("integration_connection.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(String(80))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class IntegrationOAuthStateModel(Base):
    __tablename__ = "integration_oauth_state"
    __table_args__ = (
        CheckConstraint(
            "provider = 'google_calendar'",
            name="integration_oauth_state_provider",
        ),
        UniqueConstraint("nonce_hash", name="uq_integration_oauth_state_nonce"),
        Index(
            "ix_integration_oauth_state_org_integration",
            "organization_id",
            "integration_connection_id",
        ),
        Index("ix_integration_oauth_state_expires", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    integration_connection_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("integration_connection.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
