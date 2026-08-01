from uuid import UUID

from app.application.channel.conversation_handler import ChannelConversationHandler
from app.application.channel.messaging import ChannelMessageHandler
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.domain.channel.contracts import InboundChannelMessage, OutboundChannelMessage


class ManagedChannelConversationHandler(ChannelMessageHandler):
    """Orchestrates administrative history around the unchanged conversation flow."""

    def __init__(
        self,
        handler: ChannelConversationHandler,
        management: ConversationManagementService,
        handoff: HumanHandoffService | None = None,
    ) -> None:
        self._handler = handler
        self._management = management
        self._handoff = handoff

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        conversation_id = self._handler.conversation_id_for(message)
        receipt_id = message.metadata.get("receipt_id")
        if not isinstance(receipt_id, str):
            raise ValueError("managed message receipt is required")
        self._management.record_inbound(
            message,
            conversation_id,
            UUID(receipt_id),
        )
        if self._handoff is not None and self._handoff.blocks_bot(
            message.resolved_context.organization_id,
            conversation_id,
        ):
            self._management.mark_inbound_processed(
                message.external_message_id,
                message.channel_type,
            )
            return OutboundChannelMessage(
                channel_type=message.channel_type,
                external_recipient_id=message.external_sender_id,
                text="",
                metadata={
                    "conversation_id": str(conversation_id),
                    "handoff_blocked": True,
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
        return outbound.model_copy(update={"metadata": metadata})
