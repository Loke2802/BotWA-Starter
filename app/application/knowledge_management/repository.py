from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.knowledge_management.contracts import KnowledgeEntryStatus
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel


class KnowledgeEntryRepository(ABC):
    @abstractmethod
    def add(self, entry: KnowledgeEntryModel) -> None: ...

    @abstractmethod
    def get_scoped(
        self,
        entry_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
    ) -> KnowledgeEntryModel | None: ...

    @abstractmethod
    def list_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> list[KnowledgeEntryModel]: ...

    @abstractmethod
    def count_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
    ) -> int: ...

    @abstractmethod
    def list_published(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        search: str | None,
        limit: int,
    ) -> list[KnowledgeEntryModel]: ...

    @abstractmethod
    def delete(self, entry: KnowledgeEntryModel) -> None: ...
