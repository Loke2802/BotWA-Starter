from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.conversation.mapper import ConversationMapper
from app.core.conversation.router import MessageRouter
from app.domain.conversation.contracts import (
    ChannelResponse,
    ConversationContext,
    ConversationMessage,
)
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.repositories.message_repository import MessageRepository


class ConversationService:
    def __init__(
        self,
        router: MessageRouter,
        mapper: ConversationMapper,
        session: Session | None = None,
        conversation_repo: ConversationRepository | None = None,
        message_repo: MessageRepository | None = None,
    ) -> None:
        self._router = router
        self._mapper = mapper
        self._session = session
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo

    def handle_message(self, message: ConversationMessage) -> ChannelResponse:
        context = ConversationContext.from_message(message)
        business_response = self._router.route(context)
        response = self._mapper.to_channel_response(business_response)

        self._persist(message, business_response.message)

        return response

    def _persist(self, message: ConversationMessage, response_message: str) -> None:
        if self._session is None:
            return

        assert self._conversation_repo is not None
        assert self._message_repo is not None

        now = datetime.now(UTC)
        conv = ConversationModel(
            id=message.conversation_id,
            company_id=message.company_id,
            customer_id=message.customer_id,
            channel="http",
            status="active",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        self._conversation_repo.add(conv)

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
