from app.core.knowledge.in_memory_provider import InMemoryKnowledgeProvider
from app.core.knowledge.orchestrator import KnowledgeOrchestrator
from app.core.knowledge.provider import KnowledgeProvider
from app.domain.knowledge.contracts import KnowledgeQuery, KnowledgeResult


class AlwaysEmptyProvider(KnowledgeProvider):
    def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        return KnowledgeResult(found=False)


def test_orchestrator_returns_first_match() -> None:
    provider = InMemoryKnowledgeProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    query = KnowledgeQuery(content="¿Cuál es el horario?", intent="question")

    result = orchestrator.search(query)

    assert result.found is True


def test_orchestrator_returns_not_found_when_no_provider_matches() -> None:
    provider = AlwaysEmptyProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    query = KnowledgeQuery(content="anything", intent="unknown")

    result = orchestrator.search(query)

    assert result.found is False


def test_orchestrator_uses_multiple_providers() -> None:
    empty = AlwaysEmptyProvider()
    real = InMemoryKnowledgeProvider()
    orchestrator = KnowledgeOrchestrator(providers=[empty, real])
    query = KnowledgeQuery(content="¿Cómo puedo pagar?", intent="question")

    result = orchestrator.search(query)

    assert result.found is True
    assert "tarjetas" in result.content.lower()
