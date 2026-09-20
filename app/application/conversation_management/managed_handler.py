from collections.abc import Callable
from uuid import UUID

from app.application.automation_management.service import ManagedAutomationService
from app.application.channel.conversation_handler import ChannelConversationHandler
from app.application.channel.messaging import ChannelMessageHandler
from app.application.contacts.service import ContactResolutionService
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.generative_ai.ingress import AIIngress
from app.application.human_handoff.service import HumanHandoffService
from app.core.business.intent_classifier import IntentClassifier
from app.domain.channel.contracts import (
    InboundChannelMessage,
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.observability.metrics import safe_metric


class ManagedChannelConversationHandler(ChannelMessageHandler):
    """Orchestrates administrative history around the unchanged conversation flow."""

    def __init__(
        self,
        handler: ChannelConversationHandler,
        management: ConversationManagementService,
        handoff: HumanHandoffService | None = None,
        contacts: ContactResolutionService | None = None,
        automations: ManagedAutomationService | None = None,
        lead_notification_recipients: (
            tuple[str, ...] | Callable[[ResolvedChannelContext], tuple[str, ...]]
        ) = (),
        ai_ingress: AIIngress | None = None,
    ) -> None:
        self._ai_ingress = ai_ingress
        self._handler = handler
        self._management = management
        self._handoff = handoff
        self._contacts = contacts
        self._automations = automations
        self._lead_notification_recipients = lead_notification_recipients

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        recipients = (
            self._lead_notification_recipients(message.resolved_context)
            if callable(self._lead_notification_recipients)
            else self._lead_notification_recipients
        )
        conversation_id = self._handler.conversation_id_for(message)
        receipt_id = message.metadata.get("receipt_id")
        if not isinstance(receipt_id, str):
            raise ValueError("managed message receipt is required")
        contact_id = None
        if self._contacts is not None:
            contact_id = self._contacts.resolve(
                message.resolved_context.organization_id,
                message.channel_type,
                message.external_sender_id,
            ).id
        conversation = self._management.record_inbound(
            message,
            conversation_id,
            UUID(receipt_id),
            contact_id,
        )
        if self._automations is not None:
            self._automations.record_inbound(
                organization_id=message.resolved_context.organization_id,
                bot_id=message.resolved_context.bot_id,
                conversation_id=conversation.id,
                contact_id=contact_id,
                channel_type=message.channel_type,
                received_at=message.timestamp,
                business_hours_state=self._automations.business_hours_state(
                    message.resolved_context.organization_id,
                    message.resolved_context.bot_id,
                    message.timestamp,
                ),
                source_receipt_id=UUID(receipt_id),
            )
        if self._handoff is not None and self._handoff.blocks_bot(
            message.resolved_context.organization_id,
            conversation_id,
        ):
            safe_metric("record_handoff", "bot_reply_suppressed", "success")
            self._management.mark_inbound_processed(
                message.external_message_id,
                message.channel_type,
            )
            return OutboundChannelMessage(
                channel_type=message.channel_type,
                external_recipient_id=message.external_sender_id,
                text="handoff-suppressed",
                metadata={
                    "conversation_id": str(conversation_id),
                    "handoff_blocked": True,
                },
            )
        if self._ai_ingress is not None and self._ai_ingress.enqueue(
            message, conversation_id
        ):
            self._management.mark_inbound_processed(
                message.external_message_id, message.channel_type
            )
            return OutboundChannelMessage(
                channel_type=message.channel_type,
                external_recipient_id=message.external_sender_id,
                text="ai-queued",
                metadata={"conversation_id": str(conversation_id), "ai_queued": True},
            )
        completed_lead_intent = (
            self._management.complete_lead_capture(conversation) if recipients else None
        )
        if completed_lead_intent is not None:
            self._management.mark_inbound_processed(
                message.external_message_id,
                message.channel_type,
            )
            return OutboundChannelMessage(
                channel_type=message.channel_type,
                external_recipient_id=message.external_sender_id,
                text="Gracias. Hemos recibido los datos para su revisión.",
                reply_to_external_message_id=message.external_message_id,
                metadata={
                    "conversation_id": str(conversation_id),
                    "lead_notification_recipients": ",".join(recipients),
                    "lead_notification_text": (
                        "Nuevo prospecto de Luri\n"
                        f"Tipo de solicitud: {completed_lead_intent}\n"
                        f"Cliente WhatsApp: {message.external_sender_id}\n"
                        f"Datos compartidos: {message.text}"
                    ),
                },
            )
        try:
            outbound = self._handler.handle(message)
        except Exception:
            self._management.mark_inbound_failed(
                message.external_message_id,
                message.channel_type,
            )
            raise
        self._management.mark_inbound_processed(
            message.external_message_id,
            message.channel_type,
        )
        metadata = dict(outbound.metadata)
        metadata["conversation_id"] = str(conversation_id)
        intent = IntentClassifier().classify(message.text)
        if (
            intent in {"lead_qualification", "human_handoff", "price_inquiry"}
            and recipients
        ):
            self._management.start_lead_capture(conversation, intent)
        return outbound.model_copy(update={"metadata": metadata})
