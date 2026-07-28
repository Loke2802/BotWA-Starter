from uuid import uuid4

from app.core.business.action_planner import ActionPlanner
from app.core.business.confidence_evaluator import ConfidenceEvaluator
from app.core.business.context_interpreter import ContextInterpreter
from app.core.business.customer_profile_provider import (
    InMemoryCustomerProfileProvider,
)
from app.core.business.decision_maker import DecisionMaker
from app.core.business.event_publisher import BusinessEventPublisher
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.rule_evaluator import RuleEvaluator
from app.core.business.service import BusinessBrainService
from app.core.knowledge.in_memory_retriever import InMemoryKnowledgeRetriever
from app.core.knowledge.normalizer import ContentNormalizer
from app.core.knowledge.publisher import InMemoryKnowledgePublisher
from app.core.knowledge.resolver import BestMatchResolver
from app.core.knowledge.service import KnowledgeService
from app.core.knowledge.validator import QualityValidator
from app.domain.business.contracts import BusinessRequest


def _full_service(
    knowledge_service: KnowledgeService | None = None,
) -> BusinessBrainService:
    profile_provider = InMemoryCustomerProfileProvider()
    return BusinessBrainService(
        intent_classifier=IntentClassifier(),
        context_interpreter=ContextInterpreter(
            customer_profile_provider=profile_provider,
        ),
        rule_evaluator=RuleEvaluator(),
        decision_maker=DecisionMaker(),
        confidence_evaluator=ConfidenceEvaluator(),
        action_planner=ActionPlanner(),
        event_publisher=BusinessEventPublisher(),
        knowledge_service=knowledge_service,
    )


def test_business_brain_returns_decision_for_greeting() -> None:
    service = _full_service()
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


def test_business_brain_with_context_interpreter() -> None:
    profile_provider = InMemoryCustomerProfileProvider()
    service = BusinessBrainService(
        intent_classifier=IntentClassifier(),
        context_interpreter=ContextInterpreter(
            customer_profile_provider=profile_provider,
        ),
        rule_evaluator=RuleEvaluator(),
        decision_maker=DecisionMaker(),
        confidence_evaluator=ConfidenceEvaluator(),
        action_planner=ActionPlanner(),
        event_publisher=BusinessEventPublisher(),
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
    service = _full_service()
    request = BusinessRequest(
        content="xyz123",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "rejected"
    assert decision.intent == "unknown"
    assert decision.confidence == "low"


def _make_knowledge_service() -> KnowledgeService:
    return KnowledgeService(
        retriever=InMemoryKnowledgeRetriever(),
        normalizer=ContentNormalizer(),
        resolver=BestMatchResolver(),
        validator=QualityValidator(),
        publisher=InMemoryKnowledgePublisher(),
    )


def test_business_brain_queries_knowledge_for_price_inquiry() -> None:
    knowledge_service = _make_knowledge_service()
    service = _full_service(knowledge_service=knowledge_service)
    request = BusinessRequest(
        content="¿Cuál es el horario de atención?",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "accepted"
    assert decision.knowledge_content is not None
    assert "horario" in decision.knowledge_content.lower()
    assert decision.confidence == "high"


def test_business_brain_stores_constraints() -> None:
    service = _full_service()
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    service.process(request)

    assert service._last_constraints is not None
    assert len(service._last_constraints.constraints) == 3
    assert service._last_options is not None
    assert service._last_confidence is not None
    assert service._last_action_plan is not None
    assert service._last_action_plan.total_steps == 1
    assert service._last_action_plan.steps[0].action == "respond"
    assert service._last_events is not None
    assert len(service._last_events) == 3


def test_business_brain_falls_back_to_policy_when_no_knowledge_found() -> None:
    knowledge_service = _make_knowledge_service()
    service = _full_service(knowledge_service=knowledge_service)
    request = BusinessRequest(
        content="¿Cómo hago para contactarlos?",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = service.process(request)

    assert decision.status == "accepted"
    assert decision.knowledge_content is None
    assert decision.confidence == "high"
