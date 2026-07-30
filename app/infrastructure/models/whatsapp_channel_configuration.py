from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class WhatsAppChannelConfigurationModel(Base):
    __tablename__ = "whatsapp_channel_configuration"
    __table_args__ = (
        UniqueConstraint(
            "phone_number_id",
            name="uq_whatsapp_channel_configuration_phone_number_id",
        ),
        UniqueConstraint(
            "public_webhook_id",
            name="uq_whatsapp_channel_configuration_public_webhook_id",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive')",
            name="whatsapp_channel_configuration_status",
        ),
        Index(
            "ix_whatsapp_channel_configuration_organization_bot_status",
            "organization_id",
            "bot_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organization.id"),
        nullable=False,
        index=True,
    )
    bot_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("bot.id"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(100), nullable=False)
    whatsapp_business_account_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    public_webhook_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        index=True,
    )
    webhook_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    verify_token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("app_user.id"),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("app_user.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return (
            "WhatsAppChannelConfigurationModel("
            f"id={self.id!r}, status={self.status!r})"
        )
