from uuid import uuid4

from app.core.business.decision_engine import DecisionEngine
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.policy import BusinessPolicy
from app.core.business.service import BusinessBrainService
from app.core.knowledge.in_memory_provider import InMemoryKnowledgeProvider
from app.core.knowledge.orchestrator import KnowledgeOrchestrator
from app.core.knowledge.service import KnowledgeService
from app.domain.business.contracts import BusinessRequest


def test_business_brain_returns_decision_for_greeting() -> None:
    intent_classifier = IntentClassifier()
    policy = BusinessPolicy()
    decision_engine = DecisionEngine(policy=policy)
    service = BusinessBrainService(
        intent_classifier=intent_classifier,
        decision_engine=decision_engine,
    )
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "accepted"
    assert decision.intent == "greeting"
    assert decision.confidence == "high"


def test_business_brain_returns_decision_for_unknown() -> None:
    intent_classifier = IntentClassifier()
    policy = BusinessPolicy()
    decision_engine = DecisionEngine(policy=policy)
    service = BusinessBrainService(
        intent_classifier=intent_classifier,
        decision_engine=decision_engine,
    )
    request = BusinessRequest(
        content="xyz123",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "accepted"
    assert decision.intent == "unknown"
    assert decision.confidence == "low"


def test_business_brain_queries_knowledge_for_price_inquiry() -> None:
    intent_classifier = IntentClassifier()
    policy = BusinessPolicy()
    decision_engine = DecisionEngine(policy=policy)
    provider = InMemoryKnowledgeProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    knowledge_service = KnowledgeService(orchestrator=orchestrator)
    service = BusinessBrainService(
        intent_classifier=intent_classifier,
        decision_engine=decision_engine,
        knowledge_service=knowledge_service,
    )
    request = BusinessRequest(
        content="¿Cuál es el horario de atención?",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "accepted"
    assert "horario" in decision.message.lower()
    assert decision.confidence == "high"


def test_business_brain_falls_back_to_policy_when_no_knowledge_found() -> None:
    intent_classifier = IntentClassifier()
    policy = BusinessPolicy()
    decision_engine = DecisionEngine(policy=policy)
    provider = InMemoryKnowledgeProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    knowledge_service = KnowledgeService(orchestrator=orchestrator)
    service = BusinessBrainService(
        intent_classifier=intent_classifier,
        decision_engine=decision_engine,
        knowledge_service=knowledge_service,
    )
    request = BusinessRequest(
        content="¿Cómo hago para contactarlos?",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "accepted"
    assert (
        decision.message == "Déjame revisar la información para responder tu consulta."
    )
    assert decision.confidence == "medium"
