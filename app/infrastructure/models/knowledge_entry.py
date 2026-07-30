from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class KnowledgeEntryModel(Base):
    __tablename__ = "knowledge_entry"
    __table_args__ = (
        Index(
            "ix_knowledge_entry_organization_bot_status",
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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
    )
    metadata_data: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
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
