from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery
from app.infrastructure.repositories.knowledge_catalog_repository import (
    KnowledgeCatalogRepository,
)


class DbKnowledgeCatalog:
    def __init__(
        self,
        catalog_repository: KnowledgeCatalogRepository,
    ) -> None:
        self._repo = catalog_repository

    def search(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        entries = self._repo.search_by_keywords(query.content)
        return [
            KnowledgeItem(
                source_id=entry.source_id,
                content=entry.content,
                confidence=entry.confidence,
                source_trust_level=entry.source_trust_level,
            )
            for entry in entries
        ]
