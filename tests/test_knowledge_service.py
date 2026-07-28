from app.core.knowledge.in_memory_retriever import InMemoryKnowledgeRetriever
from app.core.knowledge.normalizer import ContentNormalizer
from app.core.knowledge.publisher import InMemoryKnowledgePublisher
from app.core.knowledge.resolver import BestMatchResolver
from app.core.knowledge.retriever import KnowledgeRetriever
from app.core.knowledge.service import KnowledgeService
from app.core.knowledge.validator import QualityValidator
from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery


class EmptyRetriever(KnowledgeRetriever):
    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        return []


def _service() -> KnowledgeService:
    return KnowledgeService(
        retriever=InMemoryKnowledgeRetriever(),
        normalizer=ContentNormalizer(),
        resolver=BestMatchResolver(),
        validator=QualityValidator(),
        publisher=InMemoryKnowledgePublisher(),
    )


def test_knowledge_service_returns_result() -> None:
    service = _service()
    query = KnowledgeQuery(
        content="¿Cuál es el horario de atención?", intent="question"
    )

    result = service.query(query)

    assert result.found is True
    assert "horario" in result.content.lower()


def test_knowledge_service_returns_not_found() -> None:
    service = KnowledgeService(
        retriever=EmptyRetriever(),
        normalizer=ContentNormalizer(),
        resolver=BestMatchResolver(),
        validator=QualityValidator(),
        publisher=InMemoryKnowledgePublisher(),
    )
    query = KnowledgeQuery(content="something unknown", intent="unknown")

    result = service.query(query)

    assert result.found is False


def test_knowledge_service_returns_validated_content() -> None:
    service = _service()
    query = KnowledgeQuery(
        content="¿Cuál es el horario de atención?", intent="question"
    )

    result = service.query(query)

    assert result.found is True
    assert result.version == 1
    assert result.confidence == "high"
