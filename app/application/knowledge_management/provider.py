from uuid import UUID

from app.application.knowledge_management.repository import KnowledgeEntryRepository
from app.domain.knowledge_management.contracts import KnowledgeEntry
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel


def knowledge_entry_from_model(model: KnowledgeEntryModel) -> KnowledgeEntry:
    return KnowledgeEntry(
        id=model.id,
        organization_id=model.organization_id,
        bot_id=model.bot_id,
        title=model.title,
        content=model.content,
        status=model.status,
        source_type=model.source_type,
        metadata=model.metadata_data,
        created_by_user_id=model.created_by_user_id,
        updated_by_user_id=model.updated_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class BotKnowledgeProvider:
    def __init__(self, repository: KnowledgeEntryRepository) -> None:
        self._repository = repository

    def retrieve_published(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        search: str | None = None,
        limit: int = 20,
    ) -> list[KnowledgeEntry]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        models = self._repository.list_published(
            organization_id,
            bot_id,
            search=search,
            limit=limit,
        )
        return [knowledge_entry_from_model(model) for model in models]
