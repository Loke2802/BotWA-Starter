from uuid import UUID

from app.application.channel.conversation_handler import ChannelConversationHandler
from app.application.channel.messaging import ChannelMessageHandler
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.domain.channel.contracts import InboundChannelMessage, OutboundChannelMessage


class ManagedChannelConversationHandler(ChannelMessageHandler):
    """Orchestrates administrative history around the unchanged conversation flow."""

    def __init__(
        self,
        handler: ChannelConversationHandler,
        management: ConversationManagementService,
    ) -> None:
        self._handler = handler
        self._management = management

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
