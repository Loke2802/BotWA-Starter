from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class KnowledgeCatalogEntryModel(Base):
    __tablename__ = "knowledge_catalog_entry"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    health_score: Mapped[float] = mapped_column(Float, default=1.0)
    source_trust_level: Mapped[float] = mapped_column(Float, default=1.0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    valid_until: Mapped[datetime | None] = mapped_column(
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
