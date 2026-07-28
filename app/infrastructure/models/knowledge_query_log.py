from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class KnowledgeQueryLogModel(Base):
    __tablename__ = "knowledge_query_log"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(50), nullable=False)
    response_found: Mapped[bool] = mapped_column(Boolean, default=False)
    response_source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
