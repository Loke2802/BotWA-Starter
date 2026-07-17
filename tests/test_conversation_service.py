from app.core.business.decision_engine import DecisionEngine
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.policy import BusinessPolicy
from app.core.business.service import BusinessBrainService
from app.core.conversation.mapper import ConversationMapper
from app.core.conversation.router import MessageRouter
from app.core.conversation.service import ConversationService
from app.domain.conversation.contracts import ConversationMessage


def test_conversation_service_returns_channel_response() -> None:
    intent_classifier = IntentClassifier()
    policy = BusinessPolicy()
    decision_engine = DecisionEngine(policy=policy)
    business_brain = BusinessBrainService(
        intent_classifier=intent_classifier,
        decision_engine=decision_engine,
    )
    service = ConversationService(
        router=MessageRouter(business_brain=business_brain),
        mapper=ConversationMapper(),
    )
    message = ConversationMessage(
        content="Hello",
        customer_id="customer-1",
        company_id="company-1",
    )

    response = service.handle_message(message)

    assert response.status == "accepted"
    assert (
        response.message == "Gracias por tu mensaje. Estamos procesando tu solicitud."
    )
