"""Optional durable response stages on the existing job and fenced lease."""

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.application.generative_ai.response_context import build_context
from app.application.generative_ai.response_validation import (
    digest,
    validate_draft,
    validate_review,
)
from app.domain.generative_ai.contracts import AdviserResult, AIConfig, ProviderError
from app.domain.generative_ai.response_contracts import (
    ConversationalDraft,
    SemanticReview,
)
from app.infrastructure.models.ai_generation import (
    AIJobModel,
    AIMemoryModel,
    AIResponseCheckpointModel,
)

if TYPE_CHECKING:
    from app.application.generative_ai.service import AIService


def check_memory(
    session: Session,
    job: AIJobModel,
    checkpoint: AIResponseCheckpointModel,
    *,
    committed: bool = False,
) -> None:
    if checkpoint.schema_version != "1":
        raise ProviderError("CONTEXT_VERSION_CHANGED")
    row = session.get(AIMemoryModel, job.conversation_id)
    expected = (
        checkpoint.committed_revision if committed else checkpoint.memory_revision
    )
    if row and (row.organization_id != job.organization_id or row.bot_id != job.bot_id):
        raise ProviderError("SCOPE_MISMATCH")
    if (row.revision if row else 0) != expected:
        raise ProviderError("MEMORY_CHANGED")


def load(service: "AIService", job_id: UUID, token: UUID) -> dict[str, Any] | None:
    with service.sessions() as session:
        job = service._owned(session, job_id, token)
        if service._eligible(session, job) is None:
            raise ProviderError("POLICY_CHANGED")
        cp = session.get(AIResponseCheckpointModel, job_id)
        if cp is None:
            return None
        check_memory(session, job, cp)
        if cp.ciphertext is None:
            raise ProviderError("CHECKPOINT_MISSING")
        data: dict[str, Any] = json.loads(service.cipher.decrypt(cp.ciphertext))
        service.check_sources(session, job, data.get("used", {}))
        return data


def save(
    service: "AIService", job_id: UUID, token: UUID, data: dict[str, Any], stage: str
) -> None:
    with service.sessions() as session:
        job = service._owned(session, job_id, token)
        if service._eligible(session, job) is None:
            raise ProviderError("POLICY_CHANGED")
        cp = session.get(AIResponseCheckpointModel, job_id)
        if cp is not None:
            check_memory(session, job, cp)
            cp.ciphertext = service.cipher.encrypt(json.dumps(data))
            cp.stage = stage
            session.commit()


async def compose(
    service: "AIService",
    job_id: UUID,
    token: UUID,
    result: AdviserResult,
    config: AIConfig,
    memory: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    base_reply: str,
    used: dict[str, str],
) -> str:
    data = load(service, job_id, token)
    if data is None or result.handoff_requested:
        return base_reply
    data.update(base_reply=base_reply, used=used)
    save(service, job_id, token, data, "base_validated")
    try:
        with service.sessions() as session:
            job = service._owned(session, job_id, token)
            current = service._eligible(session, job)
            if current is None:
                raise ProviderError("POLICY_CHANGED")
            if not current.conversational_response.enabled:
                raise ProviderError("RESPONSE_DISABLED")
            cp = session.get(AIResponseCheckpointModel, job_id)
            assert cp is not None
            if cp.response_revoked:
                raise ProviderError("RESPONSE_CONFIG_CHANGED")
            context_id = str(cp.context_id)
        context = build_context(context_id, result, config, memory, sources)
        data["context"] = context.model_dump()
        save(service, job_id, token, data, "context_validated")
        # Both slots are reserved before spending anything on naturalization.
        service.reserve_response(job_id, token)
        draft = ConversationalDraft.model_validate_json(
            await service._generate(
                job_id,
                token,
                "conversational_render",
                context.model_dump(),
                ConversationalDraft,
            )
        )
        text = validate_draft(
            context, draft, service.settings.whatsapp_outbound_max_text_chars
        )
        review = SemanticReview.model_validate_json(
            await service._generate(
                job_id,
                token,
                "semantic_review",
                {
                    "context": context.model_dump(),
                    "draft": draft.model_dump(),
                    "expanded_text": text,
                    "draft_digest": digest(text),
                },
                SemanticReview,
            )
        )
        validate_review(context, draft, text, review)
        outcome, reason = "approved", None
    except (ProviderError, ValidationError) as exc:
        if isinstance(exc, ProviderError) and exc.code in {
            "POLICY_CHANGED",
            "MEMORY_CHANGED",
            "SCOPE_MISMATCH",
            "SOURCE_CHANGED",
            "LOST_LEASE",
            "CONTEXT_VERSION_CHANGED",
        }:
            raise
        text, outcome = base_reply, "fallback"
        reason = exc.code if isinstance(exc, ProviderError) else "INVALID_SCHEMA"
    with service.sessions() as session:
        job = service._owned(session, job_id, token)
        cp = session.get(AIResponseCheckpointModel, job_id)
        assert cp is not None
        cp.outcome, cp.reason_code = outcome, reason
        cp.reply_digest = digest(text)
        service.release_reservations(session, job_id)
        session.commit()
    return text
