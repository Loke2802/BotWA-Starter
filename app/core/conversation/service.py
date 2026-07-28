from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.conversation.channel_adapter import ChannelAdapter
from app.core.conversation.context_builder import ConversationContextBuilder
from app.core.conversation.response_composer import ResponseComposer
from app.core.conversation.router import MessageRouter
from app.core.conversation.state_manager import ConversationStateManager
from app.core.conversation.topic_detector import TopicDetector
from app.domain.conversation.contracts import (
    ChannelResponse,
    ConversationMessage,
)
from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.repositories.message_repository import MessageRepository


class ConversationService:
    def __init__(
        self,
        router: MessageRouter,
        adapters: Mapping[str, ChannelAdapter],
        state_manager: ConversationStateManager,
        context_builder: ConversationContextBuilder,
        topic_detector: TopicDetector,
        response_composer: ResponseComposer,
        session: Session | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
    ) -> None:
        self._router = router
        self._adapters: Mapping[str, ChannelAdapter] = adapters
        self._state_manager = state_manager
        self._context_builder = context_builder
        self._topic_detector = topic_detector
        self._response_composer = response_composer
        self._session = session
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo

    def handle_message(self, message: ConversationMessage) -> ChannelResponse:
        state = self._state_manager.get_or_create(
            conversation_id=message.conversation_id,
            company_id=message.company_id,
            customer_id=message.customer_id,
        )

        if self._state_manager.is_terminal(state.current_state):
            return ChannelResponse(
                status="rejected",
                message="La conversación se encuentra finalizada.",
            )

        if state.current_state == "new":
            self._state_manager.transition(message.conversation_id, "in_progress")

        self._state_manager.transition(message.conversation_id, "awaiting_brain")

        context = self._context_builder.build(message, state)
        context = self._topic_detector.detect(context)
        business_decision = self._router.route(context)

        self._state_manager.transition(message.conversation_id, "in_progress")

        business_response = self._response_composer.compose(
            business_decision,
            context,
        )
        adapter = self._get_adapter(message.channel)
        response = adapter.adapt(business_response)

        self._persist(message, business_response.message)

        return response

    def _get_adapter(self, channel: str) -> ChannelAdapter:
        return self._adapters.get(channel, self._adapters["http"])

    def _persist(self, message: ConversationMessage, response_message: str) -> None:
        if self._session is None:
            return

        assert self._message_repo is not None

        now = datetime.now(UTC)

        msg = MessageModel(
            id=uuid4(),
            conversation_id=message.conversation_id,
            role="user",
            content=message.content,
            created_at=now,
        )
        self._message_repo.add(msg)

        reply = MessageModel(
            id=uuid4(),
            conversation_id=message.conversation_id,
            role="assistant",
            content=response_message,
            created_at=now,
        )
        self._message_repo.add(reply)

        self._session.commit()
