from app.domain.knowledge.contracts import (
    KnowledgeContext,
    KnowledgeItem,
    KnowledgeQuery,
    KnowledgeResponse,
    KnowledgeResult,
    KnowledgeSource,
    NormalizedKnowledgeItem,
    ResolvedKnowledgeItem,
    ValidatedKnowledgeItem,
)


def test_knowledge_query_holds_content_and_intent() -> None:
    query = KnowledgeQuery(
        content="¿Cuál es el horario?",
        intent="question",
        customer_id="customer-1",
        company_id="company-1",
    )

    assert query.content == "¿Cuál es el horario?"
    assert query.intent == "question"
    assert query.customer_id == "customer-1"
    assert query.company_id == "company-1"


def test_knowledge_query_defaults() -> None:
    query = KnowledgeQuery(content="test", intent="unknown")

    assert query.customer_id == ""
    assert query.company_id == ""


def test_knowledge_context_holds_query() -> None:
    query = KnowledgeQuery(content="test", intent="unknown")
    context = KnowledgeContext(query=query)

    assert context.query == query
    assert context.created_at is not None


def test_knowledge_result_found() -> None:
    result = KnowledgeResult(
        found=True,
        content="Answer here",
        confidence="high",
    )

    assert result.found is True
    assert result.content == "Answer here"
    assert result.confidence == "high"


def test_knowledge_result_not_found() -> None:
    result = KnowledgeResult(found=False)

    assert result.found is False
    assert result.content == ""
    assert result.confidence == "low"


def test_knowledge_source_holds_fields() -> None:
    source = KnowledgeSource(
        source_id="src-1",
        name="Seed Data",
        type="in_memory",
        trust_level=1.0,
    )

    assert source.source_id == "src-1"
    assert source.name == "Seed Data"
    assert source.status == "active"


def test_knowledge_item_holds_fields() -> None:
    item = KnowledgeItem(
        source_id="src-1",
        content="Some content",
        confidence="high",
    )

    assert item.source_id == "src-1"
    assert item.content == "Some content"
    assert item.retrieved_at is not None


def test_normalized_knowledge_item_holds_fields() -> None:
    item = NormalizedKnowledgeItem(
        source_id="src-1",
        canonical_content="Normalized",
        confidence="high",
    )

    assert item.canonical_content == "Normalized"
    assert item.normalized_at is not None


def test_resolved_knowledge_item_holds_fields() -> None:
    item = ResolvedKnowledgeItem(
        sources=["src-1", "src-2"],
        content="Resolved",
        resolution_strategy="first_match",
    )

    assert item.content == "Resolved"
    assert len(item.sources) == 2
    assert item.resolved_at is not None


def test_validated_knowledge_item_holds_fields() -> None:
    item = ValidatedKnowledgeItem(
        source_id="src-1",
        content="Validated",
        health_score=0.95,
    )

    assert item.health_score == 0.95
    assert item.validity_status == "approved"
    assert item.validated_at is not None


def test_knowledge_response_found() -> None:
    response = KnowledgeResponse(
        found=True,
        content="Response content",
        confidence="high",
        sources=["src-1"],
    )

    assert response.found is True
    assert response.content == "Response content"
    assert response.sources == ["src-1"]


def test_knowledge_response_not_found() -> None:
    response = KnowledgeResponse(found=False)

    assert response.found is False
    assert response.content == ""
    assert response.sources == []
