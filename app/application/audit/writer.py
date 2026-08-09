from datetime import UTC, datetime
from uuid import UUID

from app.domain.audit.contracts import (
    AuditAction,
    AuditActorType,
    AuditEventDraft,
    AuditMetadata,
    AuditResourceType,
    EmptyMetadata,
)
from app.domain.audit.ports import AuditWriter
from app.domain.user.contracts import User


def append_user_audit(
    writer: AuditWriter | None,
    *,
    organization_id: UUID,
    actor: User,
    action: AuditAction,
    resource_type: AuditResourceType,
    resource_id: UUID | None,
    metadata: AuditMetadata | None = None,
    correlation_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    if writer is None:
        return
    writer.append(
        AuditEventDraft(
            organization_id=organization_id,
            actor_type="user",
            actor_user_id=actor.id,
            actor_role=actor.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or EmptyMetadata(),
            correlation_id=correlation_id,
            occurred_at=occurred_at or datetime.now(UTC),
        )
    )


def append_non_user_audit(
    writer: AuditWriter | None,
    *,
    organization_id: UUID,
    actor_type: AuditActorType,
    action: AuditAction,
    resource_type: AuditResourceType,
    resource_id: UUID | None,
    metadata: AuditMetadata | None = None,
    correlation_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    if writer is None:
        return
    if actor_type == "user":
        raise ValueError("user audit events require an authenticated actor")
    writer.append(
        AuditEventDraft(
            organization_id=organization_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or EmptyMetadata(),
            correlation_id=correlation_id,
            occurred_at=occurred_at or datetime.now(UTC),
        )
    )
