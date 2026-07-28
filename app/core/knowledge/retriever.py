from abc import ABC, abstractmethod

from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery


class KnowledgeRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeItem]: ...
