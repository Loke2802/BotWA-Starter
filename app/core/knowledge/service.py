from app.core.knowledge.orchestrator import KnowledgeOrchestrator
from app.domain.knowledge.contracts import (
    KnowledgeContext,
    KnowledgeQuery,
    KnowledgeResult,
)


class KnowledgeService:
    def __init__(self, orchestrator: KnowledgeOrchestrator) -> None:
        self._orchestrator = orchestrator

    def query(self, query: KnowledgeQuery) -> KnowledgeResult:
        context = KnowledgeContext(query=query)
        return self._orchestrator.search(context.query)
