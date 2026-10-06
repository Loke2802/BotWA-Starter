from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from app.infrastructure.models.conversation import ConversationModel


class MessageModel(Base):
    __tablename__ = "message"
    __table_args__ = (
        Index(
            "ix_message_conversation_occurred", "conversation_id", "occurred_at", "id"
        ),
        Index("ix_message_organization_bot", "organization_id", "bot_id"),
        Index(
            "uq_message_inbound_external",
            "channel_type",
            "external_message_id",
            unique=True,
            postgresql_where=text(
                "(((direction)::text = 'inbound'::text) AND (external_message_id "
                "IS NOT NULL))"
            ),
            sqlite_where=text(
                "(((direction) = 'inbound') AND (external_message_id IS NOT NULL))"
            ),
        ),
        Index(
            "uq_message_outbound_attempt",
            "outbound_attempt_id",
            unique=True,
            postgresql_where=text("(outbound_attempt_id IS NOT NULL)"),
            sqlite_where=text("(outbound_attempt_id IS NOT NULL)"),
        ),
        ForeignKeyConstraint(
            ["inbound_receipt_id"],
            ["inbound_message_receipt.id"],
            name="fk_message_inbound_receipt_id_inbound_message_receipt",
        ),
        ForeignKeyConstraint(
            ["outbound_attempt_id"],
            ["outbound_message_attempt.id"],
            name="fk_message_outbound_attempt_id_outbound_message_attempt",
        ),
        CheckConstraint(
            "direction IS NULL OR (direction IN ('inbound', 'outbound'))",
            name=conv("ck_message_message_management_direction"),
        ),
        CheckConstraint(
            "delivery_status IS NULL OR (delivery_status IN ('received', "
            "'processed', 'pending', 'sent', 'delivered', 'read', 'failed'))",
            name=conv("ck_message_message_management_status"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    bot_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    author_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=True, index=True
    )
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    channel_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    text_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    inbound_receipt_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outbound_attempt_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    metadata_data: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, default=dict
    )
    extra_data: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")
