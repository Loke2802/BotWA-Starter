from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.application.access.service import AccessService
from app.application.auth.service import (
    AuthInactiveUserError,
    AuthInvalidTokenError,
    AuthService,
)
from app.application.bots.service import BotService
from app.application.business_configuration.service import (
    BusinessConfigurationService,
)
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.core.automation.event_publisher import AutomationEventPublisher
from app.core.automation.execution_monitor import WorkflowExecutionMonitor
from app.core.automation.persistent_monitor import PersistentExecutionMonitor
from app.core.automation.request_builder import DefaultAutomationRequestBuilder
from app.core.automation.service import AutomationService
from app.core.automation.task_orchestrator import SequentialTaskOrchestrator
from app.core.automation.task_registry import create_default_registry
from app.core.automation.workflow_planner import DefaultWorkflowPlanner
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
from app.core.conversation.channel_adapter import HttpChannelAdapter
from app.core.conversation.context_builder import ConversationContextBuilder
from app.core.conversation.response_composer import ResponseComposer
from app.core.conversation.router import MessageRouter
from app.core.conversation.service import ConversationService
from app.core.conversation.state_manager import ConversationStateManager
from app.core.conversation.topic_detector import TopicDetector
from app.core.integration.factory import (
    create_integration_service as _create_integration_service,
)
from app.core.integration.health_checker import HealthChecker
from app.core.integration.service import IntegrationService
from app.core.knowledge.db_catalog import DbKnowledgeCatalog
from app.core.knowledge.db_retriever import DbKnowledgeRetriever
from app.core.knowledge.in_memory_retriever import InMemoryKnowledgeRetriever
from app.core.knowledge.normalizer import ContentNormalizer
from app.core.knowledge.publisher import (
    DbKnowledgePublisher,
    InMemoryKnowledgePublisher,
    KnowledgePublisher,
)
from app.core.knowledge.resolver import BestMatchResolver
from app.core.knowledge.retriever import KnowledgeRetriever
from app.core.knowledge.seed_data import ensure_knowledge_seed_data
from app.core.knowledge.service import KnowledgeService
from app.core.knowledge.validator import QualityValidator
from app.domain.access.contracts import Permission
from app.domain.user.contracts import User
from app.infrastructure.database import get_session
from app.infrastructure.repositories.automation_execution_repository import (
    AutomationExecutionRepository,
)
from app.infrastructure.repositories.automation_task_execution_repository import (
    AutomationTaskExecutionRepository,
)
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.business_configuration_repository import (
    BusinessConfigurationRepository,
)
from app.infrastructure.repositories.business_event_repository import (
    BusinessEventRepository,
)
from app.infrastructure.repositories.conversation_repository import (
    ConversationRepository,
)
from app.infrastructure.repositories.knowledge_catalog_repository import (
    KnowledgeCatalogRepository,
)
from app.infrastructure.repositories.knowledge_query_log_repository import (
    KnowledgeQueryLogRepository,
)
from app.infrastructure.repositories.message_repository import MessageRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.settings import get_settings
from app.security.authorization import (
    AuthorizationError,
)
from app.security.authorization import (
    require_permission as authorize_permission,
)
from app.security.passwords import PasswordService
from app.security.tokens import AccessTokenService

bearer_scheme = HTTPBearer(auto_error=False)


def get_conversation_service() -> Generator[ConversationService]:
    settings = get_settings()
    intent_classifier = IntentClassifier()
    decision_maker = DecisionMaker()
    confidence_evaluator = ConfidenceEvaluator()
    action_planner = ActionPlanner()

    normalizer = ContentNormalizer()
    resolver = BestMatchResolver()
    validator = QualityValidator()

    event_publisher = BusinessEventPublisher()
    customer_profile_provider = InMemoryCustomerProfileProvider()
    context_interpreter = ContextInterpreter(
        customer_profile_provider=customer_profile_provider,
    )
    rule_evaluator = RuleEvaluator()

    session = None
    conversation_repo = None
    message_repo = None

    retriever: KnowledgeRetriever
    publisher: KnowledgePublisher
    query_log_repo = None

    session_generator: Generator[Session] | None = None

    if settings.use_database:
        session_generator = get_session()
        session = next(session_generator)
        conversation_repo = ConversationRepository(session=session)
        message_repo = MessageRepository(session=session)
        event_repo = BusinessEventRepository(session=session)
        event_publisher = BusinessEventPublisher(event_repository=event_repo)

        catalog_repo = KnowledgeCatalogRepository(session=session)
        ensure_knowledge_seed_data(catalog_repo)
        catalog = DbKnowledgeCatalog(catalog_repository=catalog_repo)
        retriever = DbKnowledgeRetriever(catalog=catalog)
        publisher = DbKnowledgePublisher(catalog_repository=catalog_repo)
        query_log_repo = KnowledgeQueryLogRepository(session=session)

        ae_event_publisher = AutomationEventPublisher(event_repository=event_repo)
        ae_exec_repo = AutomationExecutionRepository(session=session)
        ae_task_repo = AutomationTaskExecutionRepository(session=session)
        persistent_monitor = PersistentExecutionMonitor(
            execution_repo=ae_exec_repo,
            task_execution_repo=ae_task_repo,
            event_publisher=ae_event_publisher,
        )
        automation_builder = DefaultAutomationRequestBuilder()
        workflow_planner = DefaultWorkflowPlanner()
        registry = create_default_registry()
        task_orchestrator = SequentialTaskOrchestrator(
            registry=registry,
            execution_monitor=persistent_monitor,
        )
        automation_service = AutomationService(
            request_builder=automation_builder,
            workflow_planner=workflow_planner,
            task_orchestrator=task_orchestrator,
            execution_monitor=persistent_monitor,
            registry=registry,
            session_factory=get_session,  # type: ignore[arg-type]
        )
        automation_service.recover()
    else:
        retriever = InMemoryKnowledgeRetriever()
        publisher = InMemoryKnowledgePublisher()

        automation_builder = DefaultAutomationRequestBuilder()
        workflow_planner = DefaultWorkflowPlanner()
        registry = create_default_registry()
        execution_monitor = WorkflowExecutionMonitor()
        task_orchestrator = SequentialTaskOrchestrator(
            registry=registry,
            execution_monitor=execution_monitor,
        )
        automation_service = AutomationService(
            request_builder=automation_builder,
            workflow_planner=workflow_planner,
            task_orchestrator=task_orchestrator,
            execution_monitor=execution_monitor,
        )

    knowledge_service = KnowledgeService(
        retriever=retriever,
        normalizer=normalizer,
        resolver=resolver,
        validator=validator,
        publisher=publisher,
        query_log_repository=query_log_repo,
    )

    state_manager = ConversationStateManager(
        session=session,
        conversation_repo=conversation_repo,
    )

    context_builder = ConversationContextBuilder(
        state_manager=state_manager,
        message_repo=message_repo,
    )

    business_brain = BusinessBrainService(
        intent_classifier=intent_classifier,
        context_interpreter=context_interpreter,
        rule_evaluator=rule_evaluator,
        decision_maker=decision_maker,
        confidence_evaluator=confidence_evaluator,
        action_planner=action_planner,
        knowledge_service=knowledge_service,
        event_publisher=event_publisher,
        automation_service=automation_service,
    )
    router = MessageRouter(business_brain=business_brain)
    topic_detector = TopicDetector()
    response_composer = ResponseComposer()
    adapters: dict[str, HttpChannelAdapter] = {
        "http": HttpChannelAdapter(),
    }
    try:
        yield ConversationService(
            router=router,
            adapters=adapters,
            state_manager=state_manager,
            context_builder=context_builder,
            topic_detector=topic_detector,
            response_composer=response_composer,
            session=session,
            conversation_repo=conversation_repo,
            message_repo=message_repo,
        )
    finally:
        if session_generator is not None:
            session_generator.close()


def get_organization_service() -> Generator[OrganizationService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        repository = OrganizationRepository(session=session)
        yield OrganizationService(repository=repository, session=session)
    finally:
        session_generator.close()


def get_password_service() -> PasswordService:
    return PasswordService()


def get_access_token_service() -> AccessTokenService:
    settings = get_settings()
    return AccessTokenService(
        secret_key=settings.auth_secret_key,
        algorithm=settings.auth_algorithm,
        expires_minutes=settings.auth_access_token_expire_minutes,
    )


def get_user_service() -> Generator[UserService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        repository = UserRepository(session=session)
        organization_repository = OrganizationRepository(session=session)
        yield UserService(
            repository=repository,
            organization_repository=organization_repository,
            password_service=get_password_service(),
            session=session,
        )
    finally:
        session_generator.close()


def get_bot_service() -> Generator[BotService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        repository = BotRepository(session=session)
        organization_repository = OrganizationRepository(session=session)
        yield BotService(
            repository=repository,
            organization_repository=organization_repository,
            session=session,
        )
    finally:
        session_generator.close()


def get_business_configuration_service() -> Generator[BusinessConfigurationService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        repository = BusinessConfigurationRepository(session=session)
        bot_repository = BotRepository(session=session)
        organization_repository = OrganizationRepository(session=session)
        yield BusinessConfigurationService(
            repository=repository,
            bot_repository=bot_repository,
            organization_repository=organization_repository,
            session=session,
        )
    finally:
        session_generator.close()


def get_auth_service(
    user_service: Annotated[UserService, Depends(get_user_service)],
    token_service: Annotated[AccessTokenService, Depends(get_access_token_service)],
) -> AuthService:
    return AuthService(user_service=user_service, token_service=token_service)


def get_access_service() -> AccessService:
    return AccessService()


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    try:
        return auth_service.authenticate_token(credentials.credentials)
    except AuthInactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user is inactive",
        ) from exc
    except AuthInvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        ) from exc


def get_optional_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User | None:
    if credentials is None:
        return None
    return get_current_user(credentials=credentials, auth_service=auth_service)


def require_authenticated_user(
    actor: Annotated[User, Depends(get_current_user)],
) -> User:
    return actor


def require_permission(permission: Permission) -> object:
    def dependency(
        actor: Annotated[User, Depends(require_authenticated_user)],
    ) -> User:
        try:
            authorize_permission(actor, permission)
        except AuthorizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="permission denied",
            ) from exc
        return actor

    return dependency


_integration_service: IntegrationService | None = None
_integration_health_checker: HealthChecker | None = None


def get_integration_service() -> IntegrationService:
    global _integration_service, _integration_health_checker
    if _integration_service is None:
        svc, _gw, _mon, hc = _create_integration_service()
        _integration_service = svc
        _integration_health_checker = hc
    return _integration_service


def get_integration_health_checker() -> HealthChecker:
    get_integration_service()
    assert _integration_health_checker is not None
    return _integration_health_checker
