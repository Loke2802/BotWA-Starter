from app.domain.knowledge.contracts import (
    KnowledgeContext,
    KnowledgeQuery,
    KnowledgeResult,
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
