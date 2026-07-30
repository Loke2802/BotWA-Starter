from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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


class InboundMessageReceiptModel(Base):
    __tablename__ = "inbound_message_receipt"
    __table_args__ = (
        UniqueConstraint(
            "channel_type",
            "external_message_id",
            name="uq_inbound_message_receipt_channel_message",
        ),
        CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'failed')",
            name="inbound_message_receipt_status",
        ),
        Index(
            "ix_inbound_message_receipt_organization_bot_status",
            "organization_id",
            "bot_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    channel_type: Mapped[str] = mapped_column(String(30), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
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
    channel_configuration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_channel_configuration.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="received",
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
        return "InboundMessageReceiptModel(" f"id={self.id!r}, status={self.status!r})"


class OutboundMessageAttemptModel(Base):
    __tablename__ = "outbound_message_attempt"
    __table_args__ = (
        UniqueConstraint(
            "provider_message_id",
            name="uq_outbound_message_attempt_provider_message_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'sent', 'delivered', 'read', 'failed')",
            name="outbound_message_attempt_status",
        ),
        Index(
            "ix_outbound_message_attempt_organization_bot_status",
            "organization_id",
            "bot_id",
            "status",
        ),
        Index(
            "ix_outbound_message_attempt_status_next_attempt",
            "status",
            "next_attempt_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inbound_receipt_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("inbound_message_receipt.id"),
        nullable=True,
        index=True,
    )
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
    channel_configuration_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_channel_configuration.id"),
        nullable=False,
        index=True,
    )
    external_recipient_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    external_recipient_ciphertext: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    message_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_external_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            "OutboundMessageAttemptModel("
            f"id={self.id!r}, status={self.status!r}, "
            f"attempt_count={self.attempt_count!r})"
        )
