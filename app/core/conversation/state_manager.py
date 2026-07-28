from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.conversation.state import ConversationState
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.conversation_state_history import (
    ConversationStateHistoryModel,
)
from app.infrastructure.repositories.conversation_repository import (
    ConversationRepository,
)

_TRANSITIONS: dict[str, set[str]] = {
    "new": {"in_progress", "cancelled"},
    "in_progress": {
        "awaiting_info",
        "awaiting_brain",
        "completed",
        "cancelled",
        "escalated",
    },
    "awaiting_info": {"in_progress", "cancelled", "escalated"},
    "awaiting_brain": {"in_progress", "awaiting_client", "cancelled", "escalated"},
    "awaiting_client": {"in_progress", "completed", "cancelled", "escalated"},
    "completed": set(),
    "cancelled": set(),
    "escalated": set(),
}

_TERMINAL_STATES = {"completed", "cancelled", "escalated"}


class ConversationStateManager:
    def __init__(
        self,
        session: Session | None = None,
        conversation_repo: ConversationRepository | None = None,
    ) -> None:
        self._session = session
        self._conversation_repo = conversation_repo
        self._in_memory: dict[UUID, str] = {}

    def get_or_create(
        self,
        conversation_id: UUID,
        company_id: str,
        customer_id: str,
    ) -> ConversationState:
        if self._conversation_repo is not None:
            conv = self._conversation_repo.get(conversation_id)
            if conv is not None:
                return self._model_to_state(conv)
            conv = ConversationModel(
                id=conversation_id,
                company_id=company_id,
                customer_id=customer_id,
                channel="http",
                status="new",
                started_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self._conversation_repo.add(conv)
            if self._session is not None:
                self._session.flush()
            return self._model_to_state(conv)
        if conversation_id not in self._in_memory:
            self._in_memory[conversation_id] = "new"
        return ConversationState(
            conversation_id=conversation_id,
            current_state=self._in_memory[conversation_id],
        )

    def transition(self, conversation_id: UUID, target_state: str) -> ConversationState:
        current = self._get_current(conversation_id)

        if not self.can_transition(current, target_state):
            raise ValueError(f"Transition not allowed: {current} → {target_state}")

        if self._conversation_repo is not None:
            conv = self._conversation_repo.get(conversation_id)
            assert conv is not None
            conv.status = target_state
            self._conversation_repo.update(conv)
            if self._session is not None:
                history = ConversationStateHistoryModel(
                    conversation_id=conversation_id,
                    from_state=current,
                    to_state=target_state,
                )
                self._session.add(history)
            return self._model_to_state(conv)

        self._in_memory[conversation_id] = target_state
        return ConversationState(
            conversation_id=conversation_id,
            current_state=target_state,
            previous_state=current,
        )

    def can_transition(self, current_state: str, target_state: str) -> bool:
        allowed = _TRANSITIONS.get(current_state)
        if allowed is None:
            return False
        return target_state in allowed

    def _get_current(self, conversation_id: UUID) -> str:
        if self._conversation_repo is not None:
            conv = self._conversation_repo.get(conversation_id)
            if conv is not None:
                return conv.status
        return self._in_memory.get(conversation_id, "new")

    @staticmethod
    def is_terminal(state: str) -> bool:
        return state in _TERMINAL_STATES

    @staticmethod
    def _model_to_state(conv: ConversationModel) -> ConversationState:
        return ConversationState(
            conversation_id=conv.id,
            current_state=conv.status,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
