from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class AIJobModel(Base):
    __tablename__ = "ai_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'ready', 'sent', 'failed', "
            "'cancelled', 'delivery_unknown', 'handoff')",
            name="ai_job_status",
        ),
        CheckConstraint("attempts >= 0 AND sequence >= 0", name="ai_job_counters"),
        Index("ix_ai_job_due", "status", "available_at"),
        Index("ix_ai_job_scope", "organization_id", "bot_id", "conversation_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_message_receipt.id"), unique=True
    )
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organization.id"))
    bot_id: Mapped[UUID] = mapped_column(ForeignKey("bot.id"))
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversation.id"))
    configuration_id: Mapped[UUID] = mapped_column(
        ForeignKey("whatsapp_channel_configuration.id")
    )
    status: Mapped[str] = mapped_column(String(30), default="pending")
    sequence: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    config_hash: Mapped[str] = mapped_column(String(64))
    result_ciphertext: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    outbound_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("outbound_message_attempt.id"), unique=True
    )


class AIMemoryModel(Base):
    __tablename__ = "ai_memory"
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id"), primary_key=True
    )
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organization.id"))
    bot_id: Mapped[UUID] = mapped_column(ForeignKey("bot.id"))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    ciphertext: Mapped[str] = mapped_column(Text)


class AIAttemptModel(Base):
    __tablename__ = "ai_attempt"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("ai_job.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(20), default="openai")
    model: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(60), default="unknown")


class AIResponseCheckpointModel(Base):
    __tablename__ = "ai_response_checkpoint"
    __table_args__ = (
        CheckConstraint("memory_revision >= 0", name="ai_response_memory_revision"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('approved', 'fallback')",
            name="ai_response_outcome",
        ),
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("ai_job.id"), primary_key=True)
    context_id: Mapped[UUID] = mapped_column(Uuid, unique=True, default=uuid4)
    schema_version: Mapped[str] = mapped_column(String(10), default="1")
    stage: Mapped[str] = mapped_column(String(32), default="discovery_pending")
    ciphertext: Mapped[str | None] = mapped_column(Text)
    memory_revision: Mapped[int] = mapped_column(Integer)
    committed_revision: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(60))
    reply_digest: Mapped[str | None] = mapped_column(String(64))
    resumed_from: Mapped[str | None] = mapped_column(String(32))
    response_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
