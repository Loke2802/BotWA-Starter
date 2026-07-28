from app.core.business.confidence_evaluator import ConfidenceEvaluator
from app.core.business.context_interpreter import ContextInterpreter
from app.core.business.customer_profile_provider import (
    InMemoryCustomerProfileProvider,
)
from app.core.business.decision_maker import DecisionMaker
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.rule_evaluator import RuleEvaluator
from app.core.business.service import BusinessBrainService
from app.core.conversation.channel_adapter import HttpChannelAdapter
from app.core.conversation.context_builder import ConversationContextBuilder
from app.core.conversation.response_composer import ResponseComposer
from app.core.conversation.router import MessageRouter
from app.core.conversation.service import ConversationService
from app.core.conversation.state_manager import ConversationStateManager
from app.core.conversation.topic_detector import TopicDetector
from app.domain.conversation.contracts import ConversationMessage


def test_conversation_service_returns_channel_response() -> None:
    profile_provider = InMemoryCustomerProfileProvider()
    business_brain = BusinessBrainService(
        intent_classifier=IntentClassifier(),
        context_interpreter=ContextInterpreter(
            customer_profile_provider=profile_provider,
        ),
        rule_evaluator=RuleEvaluator(),
        decision_maker=DecisionMaker(),
        confidence_evaluator=ConfidenceEvaluator(),
    )
    state_manager = ConversationStateManager()
    service = ConversationService(
        router=MessageRouter(business_brain=business_brain),
        adapters={"http": HttpChannelAdapter()},
        state_manager=state_manager,
        context_builder=ConversationContextBuilder(state_manager=state_manager),
        topic_detector=TopicDetector(),
        response_composer=ResponseComposer(),
    )
    message = ConversationMessage(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
    )

    response = service.handle_message(message)

    assert response.status == "accepted"
    assert "Hola" in response.message
