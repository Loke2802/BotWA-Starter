from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from app.infrastructure.models.message import MessageModel


class ConversationModel(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Legacy Core conversations may not have product tenant identity. PRD-009
    # only exposes rows with these fields populated through scoped repositories.
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=True, index=True
    )
    bot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("bot.id"), nullable=True, index=True
    )
    channel_configuration_id: Mapped[UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    external_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    masked_customer_identifier: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    management_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )
    business_case_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="http")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    external_conversation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    extra_data: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, default=dict
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inbound_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    outbound_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    messages: Mapped[list[MessageModel]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
