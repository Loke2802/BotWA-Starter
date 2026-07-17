from abc import ABC, abstractmethod

from app.domain.knowledge.contracts import KnowledgeQuery, KnowledgeResult


class KnowledgeProvider(ABC):
    @abstractmethod
    def search(self, query: KnowledgeQuery) -> KnowledgeResult: ...
