from app.core.knowledge.in_memory_retriever import InMemoryKnowledgeRetriever
from app.core.knowledge.retriever import KnowledgeRetriever
from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery


class EmptyRetriever(KnowledgeRetriever):
    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        return []


def test_retriever_finds_horario() -> None:
    retriever = InMemoryKnowledgeRetriever()
    query = KnowledgeQuery(
        content="¿Cuál es el horario de atención?", intent="question"
    )

    items = retriever.retrieve(query)

    assert len(items) == 1
    assert "horario" in items[0].content.lower()
    assert items[0].confidence == "high"
    assert items[0].source_id == "in_memory_seed"


def test_retriever_returns_empty_for_unknown() -> None:
    retriever = InMemoryKnowledgeRetriever()
    query = KnowledgeQuery(
        content="Esto no coincide con nada conocido", intent="unknown"
    )

    items = retriever.retrieve(query)

    assert items == []


def test_retriever_finds_envio() -> None:
    retriever = InMemoryKnowledgeRetriever()
    query = KnowledgeQuery(content="¿Hacen envíos a domicilio?", intent="question")

    items = retriever.retrieve(query)

    assert len(items) == 1
    assert "envío" in items[0].content.lower()


def test_retriever_finds_pago() -> None:
    retriever = InMemoryKnowledgeRetriever()
    query = KnowledgeQuery(content="¿Qué métodos de pago aceptan?", intent="question")

    items = retriever.retrieve(query)

    assert len(items) == 1
    assert "tarjetas" in items[0].content.lower()


def test_empty_retriever_returns_empty_list() -> None:
    retriever = EmptyRetriever()
    query = KnowledgeQuery(content="anything", intent="unknown")

    items = retriever.retrieve(query)

    assert items == []
