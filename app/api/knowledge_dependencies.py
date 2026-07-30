from collections.abc import Generator

from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.knowledge_management.service import KnowledgeManagementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)


def get_knowledge_management_service() -> Generator[KnowledgeManagementService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield KnowledgeManagementService(
            repository=SqlAlchemyKnowledgeEntryRepository(session),
            bot_repository=BotRepository(session),
            organization_repository=OrganizationRepository(session),
            session=session,
        )
    finally:
        session_generator.close()


def get_bot_knowledge_provider() -> Generator[BotKnowledgeProvider]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield BotKnowledgeProvider(SqlAlchemyKnowledgeEntryRepository(session))
    finally:
        session_generator.close()
