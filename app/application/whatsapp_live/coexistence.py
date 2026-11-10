"""Persist verified Business App echoes; no provider calls or outbound work."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.channel.conversation_handler import CHANNEL_CONVERSATION_NAMESPACE
from app.application.generative_ai.service import ACTIVE, AIService
from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.domain.channel.contracts import ResolvedChannelContext
from app.domain.whatsapp_live.contracts import WhatsAppBusinessAppEcho
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
)
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.security.secret_cipher import SecretCipher

ECHO_NAMESPACE = UUID("963bf286-4449-43e6-9899-947b52e4f755")


class BusinessAppEchoService:
    def __init__(self, session: Session, cipher: SecretCipher) -> None:
        self.session, self.cipher = session, cipher

    def record(
        self, echo: WhatsAppBusinessAppEcho, context: ResolvedChannelContext
    ) -> bool:
        # Serialize echoes of one line, including first outbound-only threads.
        # The primary key is also a durable uniqueness fence across restarts.
        channel = self.session.scalar(
            select(WhatsAppChannelConfigurationModel).where(
                WhatsAppChannelConfigurationModel.id
                == context.channel_configuration_id,
                WhatsAppChannelConfigurationModel.organization_id
                == context.organization_id,
                WhatsAppChannelConfigurationModel.bot_id == context.bot_id,
                WhatsAppChannelConfigurationModel.phone_number_id
                == echo.phone_number_id,
                WhatsAppChannelConfigurationModel.status == "active",
                WhatsAppChannelConfigurationModel.webhook_enabled.is_(True),
            )
            # NO KEY UPDATE serializes echoes without blocking foreign-key
            # checks of an inbound job that already owns the conversation lock.
            .with_for_update(key_share=True)
        )
        if channel is None or echo.phone_number_id != context.external_channel_id:
            raise ValueError("Business App echo channel mismatch")
        message_id = uuid5(
            ECHO_NAMESPACE,
            f"{channel.id}:{echo.external_message_id}:{echo.message_type}",
        )
        if self.session.get(MessageModel, message_id) is not None:
            # A delayed duplicate must not reopen a handoff returned to the bot.
            return False
        now = datetime.now(UTC)
        conversation_id = uuid5(
            CHANNEL_CONVERSATION_NAMESPACE,
            f"whatsapp:{context.organization_id}:{context.bot_id}:"
            f"{echo.external_recipient_id}",
        )
        conversation, _ = SqlAlchemyConversationManagementRepository(
            self.session
        ).get_or_create(
            ConversationModel(
                id=conversation_id,
                company_id=str(context.organization_id),
                customer_id=echo.external_recipient_id,
                organization_id=context.organization_id,
                bot_id=context.bot_id,
                channel_configuration_id=channel.id,
                external_customer_id=echo.external_recipient_id,
                masked_customer_identifier=f"***{echo.external_recipient_id[-4:]}",
                channel="whatsapp",
                status="new",
                management_status="open",
                started_at=echo.timestamp,
            ),
            alternate_id=uuid5(conversation_id, f"channel_configuration:{channel.id}"),
        )
        self.session.refresh(conversation, with_for_update=True)
        if echo.message_type in {"edit", "revoke"}:
            # No unverified edit payload is treated as a new commercial fact.
            # Hide stale text from future model context while retaining the row.
            previous = self.session.scalars(
                select(MessageModel).where(
                    MessageModel.conversation_id == conversation.id,
                    MessageModel.organization_id == context.organization_id,
                    MessageModel.bot_id == context.bot_id,
                    MessageModel.provider_message_id == echo.external_message_id,
                    MessageModel.direction == "outbound",
                )
            )
            for row in previous:
                row.metadata_data = {
                    **(row.metadata_data or {}),
                    "business_app_content_invalidated": True,
                }
        text = (
            echo.text
            if echo.message_type == "text" and echo.text
            else "[Intervención desde WhatsApp Business; contenido no disponible]"
        )
        self.session.add(
            MessageModel(
                id=message_id,
                conversation_id=conversation.id,
                role="human",
                content="",
                organization_id=context.organization_id,
                bot_id=context.bot_id,
                direction="outbound",
                channel_type="whatsapp",
                provider_message_id=echo.external_message_id,
                message_type=echo.message_type,
                text_ciphertext=self.cipher.encrypt(text),
                delivery_status="sent",
                occurred_at=echo.timestamp,
                metadata_data={"source": "whatsapp_business_app"},
            )
        )
        conversation.message_count += 1
        conversation.outbound_message_count += 1
        if conversation.last_message_at is None or _utc(
            conversation.last_message_at
        ) < _utc(echo.timestamp):
            conversation.last_message_at = echo.timestamp
        if conversation.last_outbound_at is None or _utc(
            conversation.last_outbound_at
        ) < _utc(echo.timestamp):
            conversation.last_outbound_at = echo.timestamp
        HumanHandoffService(
            HumanHandoffRepository(self.session),
            self.session,
            SqlAlchemyAuditRepository(self.session),
            PlanEnforcementService(SqlAlchemyPlanRepository(self.session)),
        ).observe_business_app_reply(
            context.organization_id, context.bot_id, conversation.id
        )
        # Dispatch locks job then conversation. Skip its job lock here to avoid
        # reversing that order; it rechecks the durable handoff after acquiring
        # the conversation lock. Never clear a delivery token already in flight.
        jobs = self.session.scalars(
            select(AIJobModel)
            .where(
                AIJobModel.conversation_id == conversation.id,
                AIJobModel.organization_id == context.organization_id,
                AIJobModel.bot_id == context.bot_id,
                AIJobModel.configuration_id == channel.id,
                AIJobModel.status.in_(ACTIVE),
            )
            .with_for_update(skip_locked=True)
        )
        for job in jobs:
            attempt = (
                self.session.scalar(
                    select(OutboundMessageAttemptModel)
                    .where(OutboundMessageAttemptModel.id == job.outbound_id)
                    .with_for_update(skip_locked=True)
                )
                if job.outbound_id
                else None
            )
            if job.outbound_id is not None and attempt is None:
                # Retry holds attempt then conversation: do not wait on it while
                # owning conversation. Its own handoff check fences the send.
                continue
            if attempt is not None and (
                attempt.delivery_token is not None
                or attempt.status in {"sent", "delivered", "read"}
            ):
                continue
            job.status, job.error_code = "cancelled", "BUSINESS_APP_REPLY"
            job.token, job.lease_until, job.result_ciphertext = None, None, None
            job.completed_at = now
            AIService.release_reservations(self.session, job.id)
            if attempt is not None and attempt.status == "pending":
                attempt.status, attempt.last_error_code = "failed", "BUSINESS_APP_REPLY"
                for message in self.session.scalars(
                    select(MessageModel).where(
                        MessageModel.outbound_attempt_id == attempt.id,
                        MessageModel.organization_id == context.organization_id,
                        MessageModel.bot_id == context.bot_id,
                    )
                ):
                    message.delivery_status = "failed"
        self.session.flush()
        return True


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
