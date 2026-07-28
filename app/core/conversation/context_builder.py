from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.conversation.state_manager import ConversationStateManager
from app.domain.conversation.contracts import (
    ConversationContext,
    ConversationMessage,
    HistoryEntry,
)
from app.domain.conversation.state import ConversationState
from app.infrastructure.repositories.message_repository import MessageRepository


class ConversationContextBuilder:
    def __init__(
        self,
        state_manager: ConversationStateManager,
        message_repo: MessageRepository | None = None,
    ) -> None:
        self._state_manager = state_manager
        self._message_repo = message_repo

    def build(
        self,
        message: ConversationMessage,
        state: ConversationState,
    ) -> ConversationContext:
        return ConversationContext(
            message=message,
            context_id=uuid4(),
            created_at=datetime.now(UTC),
            state=state,
            history=self._load_history(message.conversation_id),
            customer_profile={
                "customer_id": message.customer_id,
                "company_id": message.company_id,
            },
            channel_metadata=message.metadata,
        )

    def _load_history(self, conversation_id: UUID) -> list[HistoryEntry]:
        if self._message_repo is None:
            return []
        models = self._message_repo.list(conversation_id=conversation_id)
        return [
            HistoryEntry(role=m.role, content=m.content, created_at=m.created_at)
            for m in models
        ]
