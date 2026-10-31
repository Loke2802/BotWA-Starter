"""Supervised, bounded purge of expired IA memory and transient results."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.infrastructure.models.ai_generation import (
    AIJobModel,
    AIMemoryModel,
    AIResponseCheckpointModel,
)
from app.infrastructure.models.conversation import ConversationModel

ACTIVE_JOB_STATUSES = ("pending", "running", "retry", "ready")
RETENTION = timedelta(days=30)


@dataclass(frozen=True)
class MemoryRetentionResult:
    eligible: int
    cleared: int
    skipped_active: int


def _expired(row: AIMemoryModel, cutoff: datetime) -> bool:
    if row.updated_at is None:
        return True
    updated = row.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return updated < cutoff


def inspect_memory_retention(
    session: Session,
    organization_id: UUID,
    bot_id: UUID,
    *,
    now: datetime | None = None,
    limit: int = 100,
    apply: bool = False,
) -> MemoryRetentionResult:
    """Inspect or clear one explicit tenant/bot batch; caller owns the transaction.

    The default is read-only. A live job blocks deletion; caller must commit an
    applied batch. No contact/message/history rows are modified here.
    """
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff = instant.astimezone(UTC) - RETENTION
    candidate_ids = session.scalars(
        select(AIMemoryModel.conversation_id)
        .where(
            AIMemoryModel.organization_id == organization_id,
            AIMemoryModel.bot_id == bot_id,
            or_(AIMemoryModel.updated_at.is_(None), AIMemoryModel.updated_at < cutoff),
        )
        .order_by(AIMemoryModel.conversation_id)
        .limit(limit)
    ).all()
    eligible = cleared = skipped_active = 0
    for conversation_id in candidate_ids:
        if apply:
            # Ingress and snapshot lock the same conversation before memory use.
            conversation = session.scalar(
                select(ConversationModel)
                .where(
                    ConversationModel.id == conversation_id,
                    ConversationModel.organization_id == organization_id,
                    ConversationModel.bot_id == bot_id,
                )
                .with_for_update(skip_locked=True)
            )
            if conversation is None:
                continue
        query = select(AIMemoryModel).where(
            AIMemoryModel.conversation_id == conversation_id,
            AIMemoryModel.organization_id == organization_id,
            AIMemoryModel.bot_id == bot_id,
        )
        row = session.scalar(
            query.with_for_update(skip_locked=True) if apply else query
        )
        if row is None or not _expired(row, cutoff):
            continue
        active = session.scalar(
            select(AIJobModel.id)
            .where(
                AIJobModel.conversation_id == conversation_id,
                AIJobModel.organization_id == organization_id,
                AIJobModel.bot_id == bot_id,
                AIJobModel.status.in_(ACTIVE_JOB_STATUSES),
            )
            .limit(1)
        )
        eligible += 1
        if active is not None:
            skipped_active += 1
            continue
        if apply:
            terminal_jobs = session.scalars(
                select(AIJobModel).where(
                    AIJobModel.conversation_id == conversation_id,
                    AIJobModel.organization_id == organization_id,
                    AIJobModel.bot_id == bot_id,
                )
            ).all()
            for job in terminal_jobs:
                job.result_ciphertext = None
                checkpoint = session.get(AIResponseCheckpointModel, job.id)
                if checkpoint is not None:
                    checkpoint.ciphertext = None
            session.delete(row)
            cleared += 1
    return MemoryRetentionResult(eligible, cleared, skipped_active)
