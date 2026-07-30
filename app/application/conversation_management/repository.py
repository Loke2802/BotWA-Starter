from abc import ABC, abstractmethod
from uuid import UUID

from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel


class ConversationManagementRepository(ABC):
    @abstractmethod
    def get_or_create(
        self, conversation: ConversationModel
    ) -> tuple[ConversationModel, bool]: ...

    @abstractmethod
    def get_scoped(
        self, conversation_id: UUID, organization_id: UUID
    ) -> ConversationModel | None: ...

    @abstractmethod
    def list_scoped(
        self,
        organization_id: UUID,
        *,
        bot_id: UUID | None,
        channel_type: str | None,
        management_status: str | None,
        external_customer_id: str | None,
        has_inbound: bool | None,
        has_outbound: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ConversationModel], int]: ...

    @abstractmethod
    def transition(self, conversation: ConversationModel, target: str) -> None: ...


class ConversationMessageManagementRepository(ABC):
    @abstractmethod
    def create_once(self, message: MessageModel) -> tuple[MessageModel, bool]: ...

    @abstractmethod
    def list_scoped(
        self, conversation_id: UUID, organization_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[MessageModel], int]: ...

    @abstractmethod
    def sync_outbound_attempt(
        self, outbound_attempt_id: UUID, status: str, provider_message_id: str | None
    ) -> bool: ...
