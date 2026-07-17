from uuid import uuid4

from app.core.business.decision_engine import DecisionEngine
from app.core.business.policy import BusinessPolicy
from app.domain.business.contracts import BusinessContext, BusinessRequest


def test_decision_engine_evaluates_greeting() -> None:
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )
    context = BusinessContext(request=request, intent="greeting")
    engine = DecisionEngine(policy=BusinessPolicy())

    decision = engine.evaluate(context)

    assert decision.status == "accepted"
    assert decision.intent == "greeting"
    assert decision.confidence == "high"
    assert decision.needs_knowledge is False


def test_decision_engine_sets_needs_knowledge_for_question() -> None:
    request = BusinessRequest(
        content="¿Cuál es el horario?",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )
    context = BusinessContext(request=request, intent="question")
    engine = DecisionEngine(policy=BusinessPolicy())

    decision = engine.evaluate(context)

    assert decision.intent == "question"
    assert decision.needs_knowledge is True
