from app.core.knowledge.provider import KnowledgeProvider
from app.domain.knowledge.contracts import KnowledgeQuery, KnowledgeResult


class KnowledgeOrchestrator:
    def __init__(self, providers: list[KnowledgeProvider]) -> None:
        self._providers = providers

    def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        for provider in self._providers:
            result = provider.search(query)
            if result.found:
                return result
        return KnowledgeResult(found=False)
