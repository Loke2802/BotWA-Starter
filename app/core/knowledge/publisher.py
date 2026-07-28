from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.domain.knowledge.contracts import (
    KnowledgeResponse,
    ValidatedKnowledgeItem,
)
from app.infrastructure.models.knowledge_catalog_entry import (
    KnowledgeCatalogEntryModel,
)
from app.infrastructure.repositories.knowledge_catalog_repository import (
    KnowledgeCatalogRepository,
)


class KnowledgePublisher(ABC):
    @abstractmethod
    def publish(
        self,
        item: ValidatedKnowledgeItem,
    ) -> KnowledgeResponse: ...


class InMemoryKnowledgePublisher(KnowledgePublisher):
    def __init__(self) -> None:
        self._published: list[ValidatedKnowledgeItem] = []

    def publish(
        self,
        item: ValidatedKnowledgeItem,
    ) -> KnowledgeResponse:
        if not item.content:
            return KnowledgeResponse(found=False)

        version = 1
        for prev in self._published:
            if prev.source_id == item.source_id and prev.version >= version:
                version = prev.version + 1
        self._published.append(item)

        return KnowledgeResponse(
            found=True,
            content=item.content,
            confidence=item.confidence,
            sources=[item.source_id] if item.source_id else [],
            version=version,
        )


class DbKnowledgePublisher(InMemoryKnowledgePublisher):
    def __init__(
        self,
        catalog_repository: KnowledgeCatalogRepository,
    ) -> None:
        super().__init__()
        self._repo = catalog_repository

    def publish(
        self,
        item: ValidatedKnowledgeItem,
    ) -> KnowledgeResponse:
        response = super().publish(item)
        if response.found:
            existing = self._repo.find_by_source_id(item.source_id)
            version = 1
            for entry in existing:
                if entry.version >= version:
                    version = entry.version + 1
                    entry.valid_until = datetime.now(UTC)

            entry = KnowledgeCatalogEntryModel(
                source_id=item.source_id,
                keywords=item.keywords,
                content=item.content,
                confidence=item.confidence,
                health_score=item.health_score,
                version=version,
            )
            self._repo.add(entry)

            response = KnowledgeResponse(
                found=True,
                content=item.content,
                confidence=item.confidence,
                sources=[item.source_id] if item.source_id else [],
                version=version,
            )
        return response
