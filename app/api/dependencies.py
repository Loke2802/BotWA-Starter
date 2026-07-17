from app.core.business.decision_engine import DecisionEngine
from app.core.business.event_publisher import BusinessEventPublisher
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.policy import BusinessPolicy
from app.core.business.service import BusinessBrainService
from app.core.conversation.mapper import ConversationMapper
from app.core.conversation.router import MessageRouter
from app.core.conversation.service import ConversationService
from app.core.knowledge.in_memory_provider import InMemoryKnowledgeProvider
from app.core.knowledge.orchestrator import KnowledgeOrchestrator
from app.core.knowledge.service import KnowledgeService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.business_event_repository import (
    BusinessEventRepository,
)
from app.infrastructure.repositories.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.repositories.message_repository import MessageRepository
from app.infrastructure.settings import get_settings


def get_conversation_service() -> ConversationService:
    settings = get_settings()
    intent_classifier = IntentClassifier()
    policy = BusinessPolicy()
    decision_engine = DecisionEngine(policy=policy)

    provider = InMemoryKnowledgeProvider()
    orchestrator = KnowledgeOrchestrator(providers=[provider])
    knowledge_service = KnowledgeService(orchestrator=orchestrator)

    event_publisher = BusinessEventPublisher()

    session = None
    conversation_repo = None
    message_repo = None

    if settings.use_database:
        session = next(get_session())
        conversation_repo = ConversationRepository(session=session)
        message_repo = MessageRepository(session=session)
        event_repo = BusinessEventRepository(session=session)
        event_publisher = BusinessEventPublisher(event_repository=event_repo)

    business_brain = BusinessBrainService(
        intent_classifier=intent_classifier,
        decision_engine=decision_engine,
        knowledge_service=knowledge_service,
        event_publisher=event_publisher,
    )
    router = MessageRouter(business_brain=business_brain)
    mapper = ConversationMapper()
    return ConversationService(
        router=router,
        mapper=mapper,
        session=session,
        conversation_repo=conversation_repo,
        message_repo=message_repo,
    )
