from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.generative_ai.policy import config_hash, configuration
from app.domain.channel.contracts import InboundChannelMessage
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.settings import Settings


class AIIngress:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session, self.settings = session, settings

    def enqueue(self, message: InboundChannelMessage, conversation_id: UUID) -> bool:
        context = message.resolved_context
        config = configuration(
            self.session, self.settings, context.organization_id, context.bot_id
        )
        if config is None:
            return False
        conversation = self.session.scalars(
            select(ConversationModel)
            .where(
                ConversationModel.id == conversation_id,
                ConversationModel.organization_id == context.organization_id,
                ConversationModel.bot_id == context.bot_id,
            )
            .with_for_update()
        ).one()
        receipt_id = UUID(str(message.metadata["receipt_id"]))
        exists = self.session.scalar(
            select(AIJobModel.id).where(AIJobModel.receipt_id == receipt_id)
        )
        if exists is None:
            now = datetime.now(UTC)
            self.session.add(
                AIJobModel(
                    id=uuid4(),
                    receipt_id=receipt_id,
                    organization_id=context.organization_id,
                    bot_id=context.bot_id,
                    conversation_id=conversation_id,
                    configuration_id=context.channel_configuration_id,
                    sequence=conversation.inbound_message_count,
                    created_at=now,
                    available_at=now,
                    config_hash=config_hash(config),
                )
            )
            self.session.flush()
        # Caller commits receipt, history, automations and this job together.
        return True
