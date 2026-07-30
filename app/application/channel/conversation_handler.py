from uuid import UUID, uuid5

from app.application.channel.messaging import ChannelMessageHandler
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.core.conversation.service import ConversationService
from app.domain.channel.contracts import (
    InboundChannelMessage,
    OutboundChannelMessage,
)
from app.domain.conversation.contracts import ConversationMessage

CHANNEL_CONVERSATION_NAMESPACE = UUID("a72fba71-d418-47e7-87cc-1a193c07b074")


class ChannelConversationHandler(ChannelMessageHandler):
    def __init__(
        self,
        conversation_service: ConversationService,
        knowledge_provider: BotKnowledgeProvider | None = None,
    ) -> None:
        self._conversation_service = conversation_service
        self._knowledge_provider = knowledge_provider

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        context = message.resolved_context
        metadata = dict(message.metadata)
        metadata.update(
            {
                "organization_id": str(context.organization_id),
                "bot_id": str(context.bot_id),
                "channel_configuration_id": str(
                    context.channel_configuration_id,
                ),
                "external_message_id": message.external_message_id,
            }
        )
        if self._knowledge_provider is not None:
            knowledge = self._knowledge_provider.retrieve_published(
                context.organization_id,
                context.bot_id,
                search=message.text,
                limit=20,
            )
            metadata["knowledge_match_count"] = len(knowledge)
            if knowledge:
                metadata["knowledge_entry_id"] = str(knowledge[0].id)

        conversation_id = uuid5(
            CHANNEL_CONVERSATION_NAMESPACE,
            (
                f"{message.channel_type}:{context.organization_id}:"
                f"{context.bot_id}:{message.external_sender_id}"
            ),
        )
        response = self._conversation_service.handle_message(
            ConversationMessage(
                content=message.text,
                customer_id=message.external_sender_id,
                company_id=str(context.organization_id),
                conversation_id=conversation_id,
                channel=message.channel_type,
                metadata=metadata,
                received_at=message.timestamp,
            )
        )
        return OutboundChannelMessage(
            channel_type=message.channel_type,
            external_recipient_id=message.external_sender_id,
            text=response.message,
            reply_to_external_message_id=message.external_message_id,
            metadata={"conversation_status": response.status},
        )
