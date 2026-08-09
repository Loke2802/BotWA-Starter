from collections.abc import Generator

from app.api.whatsapp_configuration_dependencies import get_whatsapp_secret_cipher
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)


def get_conversation_management_service() -> Generator[ConversationManagementService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        audit_writer = SqlAlchemyAuditRepository(session)
        yield ConversationManagementService(
            conversations=SqlAlchemyConversationManagementRepository(session),
            messages=SqlAlchemyConversationMessageManagementRepository(
                session, audit_writer
            ),
            bot_repository=BotRepository(session),
            cipher=get_whatsapp_secret_cipher(),
            session=session,
            audit_writer=audit_writer,
        )
    finally:
        session_generator.close()
