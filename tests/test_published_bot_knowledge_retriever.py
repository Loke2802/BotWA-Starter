from datetime import UTC, datetime
from uuid import uuid4

from app.api.dependencies import build_conversation_service
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.knowledge_management.retriever import (
    PublishedBotKnowledgeRetriever,
)
from app.core.conversation.service import ConversationService
from app.domain.conversation.contracts import ConversationMessage
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.repositories.knowledge_entry_repository import (
    InMemoryKnowledgeEntryRepository,
)


def test_published_bot_knowledge_answers_a_question() -> None:
    organization_id = uuid4()
    bot_id = uuid4()
    repository = InMemoryKnowledgeEntryRepository()
    repository.add(
        KnowledgeEntryModel(
            id=uuid4(),
            organization_id=organization_id,
            bot_id=bot_id,
            title="Luri overview",
            content="Luri usa WhatsApp e IA para automatizar la atencion al cliente.",
            status="published",
            source_type="manual",
            metadata_data={},
            created_by_user_id=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    service: ConversationService = build_conversation_service(
        knowledge_retriever=PublishedBotKnowledgeRetriever(
            BotKnowledgeProvider(repository),
            organization_id,
            bot_id,
        )
    )

    response = service.handle_message(
        ConversationMessage(
            content="Que es Luri?",
            customer_id="customer-1",
            company_id=str(organization_id),
            channel="whatsapp",
        ),
        persist=False,
    )

    assert response.message == (
        "Luri usa WhatsApp e IA para automatizar la atencion al cliente."
    )
