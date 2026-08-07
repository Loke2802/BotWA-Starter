from abc import ABC, abstractmethod
from uuid import UUID

from app.infrastructure.models.contact import ContactModel


class ContactRepository(ABC):
    @abstractmethod
    def get_by_identity(
        self,
        organization_id: UUID,
        channel_type: str,
        external_identifier_hash: str,
    ) -> ContactModel | None: ...

    @abstractmethod
    def get_scoped(
        self, contact_id: UUID, organization_id: UUID
    ) -> ContactModel | None: ...

    @abstractmethod
    def add(self, contact: ContactModel) -> ContactModel: ...

    @abstractmethod
    def list_scoped(
        self,
        organization_id: UUID,
        *,
        status: str | None,
        channel_type: str | None,
        bot_id: UUID | None,
        external_identifier_hash: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ContactModel], int]: ...
