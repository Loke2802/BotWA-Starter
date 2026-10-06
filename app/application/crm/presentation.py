from datetime import UTC, datetime
from typing import Literal, cast

from app.domain.crm.contracts import ActionRecord, OpportunityRecord, StageKind
from app.infrastructure.models.crm_opportunity import OpportunityModel
from app.infrastructure.repositories.crm_opportunity_repository import (
    OpportunityRepository,
)
from app.security.secret_cipher import SecretCipher


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def redact(item: OpportunityRecord) -> OpportunityRecord:
    return item.model_copy(
        update={
            "title": "Oportunidad",
            "need": None,
            "no_action_reason": None,
            "close_reason": None,
            "amount": None,
            "currency": None,
            "next_action": (
                item.next_action.model_copy(
                    update={"description": "Contenido restringido"}
                )
                if item.next_action
                else None
            ),
        }
    )


def record(
    repository: OpportunityRepository,
    cipher: SecretCipher,
    row: OpportunityModel,
    *,
    content: bool,
) -> OpportunityRecord:
    action = repository.action(row)
    stage = next(
        s for s in repository.stages(row.organization_id) if s.code == row.stage_code
    )
    item = OpportunityRecord(
        id=row.id,
        contact_id=row.contact_id,
        title=cipher.decrypt(row.title_ciphertext),
        need=cipher.decrypt(row.need_ciphertext) if row.need_ciphertext else None,
        stage_code=row.stage_code,
        stage_kind=cast(StageKind, stage.kind),
        assigned_user_id=row.assigned_user_id,
        next_action=(
            ActionRecord(
                id=action.id,
                description=cipher.decrypt(action.description_ciphertext),
                due_at=aware(action.due_at),
                status=cast("LiteralActionStatus", action.status),
            )
            if action
            else None
        ),
        no_action_reason=(
            cipher.decrypt(row.no_action_reason_ciphertext)
            if row.no_action_reason_ciphertext
            else None
        ),
        close_reason=(
            cipher.decrypt(row.close_reason_ciphertext)
            if row.close_reason_ciphertext
            else None
        ),
        amount=row.amount,
        currency=row.currency,
        version=row.version,
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
        closed_at=aware(row.closed_at) if row.closed_at else None,
    )
    return item if content else redact(item)


LiteralActionStatus = Literal["pending", "completed", "cancelled"]
