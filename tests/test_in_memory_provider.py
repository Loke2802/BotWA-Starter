from app.core.knowledge.in_memory_provider import InMemoryKnowledgeProvider
from app.domain.knowledge.contracts import KnowledgeQuery


def test_provider_finds_horario_knowledge() -> None:
    provider = InMemoryKnowledgeProvider()
    query = KnowledgeQuery(
        content="¿Cuál es el horario de atención?", intent="question"
    )

    result = provider.search(query)

    assert result.found is True
    assert "horario" in result.content.lower()
    assert result.confidence == "high"


def test_provider_finds_envio_knowledge() -> None:
    provider = InMemoryKnowledgeProvider()
    query = KnowledgeQuery(content="¿Hacen envíos a domicilio?", intent="question")

    result = provider.search(query)

    assert result.found is True
    assert "envío" in result.content.lower()


def test_provider_finds_pago_knowledge() -> None:
    provider = InMemoryKnowledgeProvider()
    query = KnowledgeQuery(content="¿Qué métodos de pago aceptan?", intent="question")

    result = provider.search(query)

    assert result.found is True
    assert "tarjetas" in result.content.lower()


def test_provider_returns_not_found_for_unknown_query() -> None:
    provider = InMemoryKnowledgeProvider()
    query = KnowledgeQuery(
        content="Esto no coincide con nada conocido", intent="unknown"
    )

    result = provider.search(query)

    assert result.found is False
