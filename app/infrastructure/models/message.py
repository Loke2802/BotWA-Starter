from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from app.infrastructure.models.conversation import ConversationModel


class MessageModel(Base):
    __tablename__ = "message"

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
        JSON, nullable=True, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")
