"""IA lane inside the automation process, never the general recovery worker."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic

import structlog
from pydantic import SecretStr
from sqlalchemy import select

from app.api.whatsapp_live_dependencies import (
    get_whatsapp_cloud_api_client,
    get_whatsapp_live_message_processor,
)
from app.application.generative_ai.service import AIService, utc
from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.domain.channel.contracts import OutboundChannelMessage, ResolvedChannelContext
from app.domain.generative_ai.contracts import ProviderError
from app.infrastructure.database import SessionLocal
from app.infrastructure.generative_ai.openai_provider import OpenAIProvider
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import get_settings
from app.infrastructure.unit_of_work import atomic_transport
from app.security.secret_cipher import EnvironmentSecretCipher

logger = structlog.get_logger(__name__)


async def dispatch_one(service: AIService) -> bool:
    """Only handles outbox entries owned by ai_job; legacy recovery stays off."""
    with service.sessions() as session:
        job = session.scalar(
            select(AIJobModel)
            .where(
                AIJobModel.status == "ready",
                AIJobModel.available_at <= datetime.now(UTC),
            )
            .order_by(AIJobModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        now = datetime.now(UTC)
        job.available_at = now + timedelta(seconds=2)
        session.scalar(
            select(ConversationModel.id)
            .where(ConversationModel.id == job.conversation_id)
            .with_for_update()
        )
        processor = get_whatsapp_live_message_processor(
            session,
            service.cipher,
            get_whatsapp_cloud_api_client(service.settings),
            service.settings,
        )
        attempt = (
            session.get(OutboundMessageAttemptModel, job.outbound_id)
            if job.outbound_id
            else None
        )
        if attempt is not None:
            if attempt.status in {"sent", "delivered", "read"}:
                job.status, job.sent_at = "sent", attempt.sent_at or now
                session.commit()
                return True
            if attempt.delivery_token is not None:
                if attempt.delivery_started_at and utc(
                    attempt.delivery_started_at
                ) < now - timedelta(seconds=120):
                    attempt.status, attempt.last_error_code = (
                        "failed",
                        "DELIVERY_UNKNOWN",
                    )
                    job.status, job.error_code = "delivery_unknown", "DELIVERY_UNKNOWN"
                    session.commit()
                session.commit()
                return False
            if attempt.status == "failed":
                job.status, job.error_code = "failed", attempt.last_error_code
                session.commit()
                return True
        try:
            if service._eligible(session, job) is None:
                raise ProviderError("POLICY_CHANGED")
            service.check_sources(session, job, job.sources)
        except ProviderError as exc:
            job.status, job.error_code = "cancelled", exc.code
            if attempt:
                attempt.status, attempt.last_error_code = "failed", exc.code
            session.commit()
            return True
        if attempt is None:
            assert job.result_ciphertext is not None
            result = json.loads(service.cipher.decrypt(job.result_ciphertext))
            if result["handoff"]:
                handoff = HumanHandoffService(
                    HumanHandoffRepository(session),
                    session,
                    SqlAlchemyAuditRepository(session),
                    PlanEnforcementService(SqlAlchemyPlanRepository(session)),
                )
                try:
                    with session.begin_nested(), atomic_transport(session):
                        handoff.request_assistant(
                            job.organization_id, job.bot_id, job.conversation_id
                        )
                except ValueError:
                    result["reply"] = (
                        "No puedo transferir esta conversación automáticamente. "
                        "Puedes contactar al negocio por su canal de atención habitual."
                    )
                else:
                    job.status = "handoff"
                    job.result_ciphertext = None
                    session.commit()
                    return True
            channel = session.get(
                WhatsAppChannelConfigurationModel, job.configuration_id
            )
            conversation = session.get(ConversationModel, job.conversation_id)
            assert channel is not None and conversation is not None
            context = ResolvedChannelContext(
                channel_type="whatsapp",
                organization_id=job.organization_id,
                bot_id=job.bot_id,
                channel_configuration_id=job.configuration_id,
                external_channel_id=channel.phone_number_id,
            )
            message = OutboundChannelMessage(
                channel_type="whatsapp",
                external_recipient_id=conversation.external_customer_id or "",
                text=result["reply"][
                    : service.settings.whatsapp_outbound_max_text_chars
                ],
                metadata={
                    "conversation_id": str(job.conversation_id),
                    "ai_job_id": str(job.id),
                },
            )
            with atomic_transport(session):
                ids = processor.enqueue_ai_reply(job.receipt_id, context, message)
                job.outbound_id = ids[0]
                job.result_ciphertext = None
            attempt_id = job.outbound_id
        else:
            attempt_id = attempt.id
            if attempt.next_attempt_at and utc(attempt.next_attempt_at) > now:
                job.available_at = attempt.next_attempt_at
                session.commit()
                return False
        session.commit()
        await processor.retry_attempt(attempt_id)
        return True


def report_queue(service: AIService) -> None:
    from app.operations.ai_metrics import snapshot

    with service.sessions() as session:
        metrics = snapshot(session)
    logger.info("ai_worker_metrics", **metrics)


def run_ai_lane(stop_event: Event, *, once: bool = False) -> None:
    settings = get_settings()
    if not settings.ai_enabled:
        return
    if settings.ai_openai_api_key is None:
        logger.error("ai_configuration_error", error_code="MISSING_PROVIDER_KEY")
    service = AIService(
        SessionLocal,
        settings,
        EnvironmentSecretCipher.from_settings(settings),
        OpenAIProvider(
            settings.ai_openai_api_key or SecretStr(""),
            settings.ai_timeout_seconds,
            settings.ai_max_output_tokens,
        ),
    )

    async def loop() -> None:
        last_report = 0.0
        while not stop_event.is_set():
            try:
                dispatched = await dispatch_one(service)
                worked = await service.run_once()
                if monotonic() - last_report >= 30:
                    report_queue(service)
                    last_report = monotonic()
            except Exception:
                logger.error("ai_lane_error", error_code="ITERATION_FAILED")
                dispatched = worked = False
            if once:
                await dispatch_one(service)
                return
            if not dispatched and not worked:
                await asyncio.to_thread(stop_event.wait, 1)

    asyncio.run(loop())
