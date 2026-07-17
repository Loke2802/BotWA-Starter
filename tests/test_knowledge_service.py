from app.core.knowledge.in_memory_provider import InMemoryKnowledgeProvider
from app.core.knowledge.orchestrator import KnowledgeOrchestrator
from app.core.knowledge.service import KnowledgeService
from app.domain.knowledge.contracts import KnowledgeQuery, KnowledgeResult


class AlwaysEmptyProvider(InMemoryKnowledgeProvider):
    def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        return KnowledgeResult(found=False)


def test_knowledge_service_returns_result() -> None:
    provider = InMemoryKnowledgeProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    service = KnowledgeService(orchestrator=orchestrator)
    query = KnowledgeQuery(
        content="¿Cuál es el horario de atención?", intent="question"
    )

    result = service.query(query)

    assert result.found is True
    assert "horario" in result.content.lower()


def test_knowledge_service_returns_not_found() -> None:
    provider = AlwaysEmptyProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    service = KnowledgeService(orchestrator=orchestrator)
    query = KnowledgeQuery(content="something unknown", intent="unknown")

    result = service.query(query)

    assert result.found is False
