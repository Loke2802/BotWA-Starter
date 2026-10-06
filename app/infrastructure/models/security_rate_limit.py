from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.infrastructure.database import Base


class SecurityRateLimitBucketModel(Base):
    __tablename__ = "security_rate_limit_bucket"
    __table_args__ = (
        Index("ix_security_rate_limit_bucket_updated_at", "updated_at"),
        CheckConstraint(
            "attempt_count >= 0",
            name=conv("ck_security_rate_limit_bucket_security_rate_limit_count_3c01"),
        ),
    )

    scope: Mapped[str] = mapped_column(String(40), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
