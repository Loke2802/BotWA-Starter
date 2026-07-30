from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.whatsapp_configuration.resolver import (
    WhatsAppChannelResolver,
)
from app.infrastructure.database import Base
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def configuration(
    organization_id: UUID,
    bot_id: UUID,
    *,
    phone_number_id: str,
    status: str,
    created_offset: int = 0,
) -> WhatsAppChannelConfigurationModel:
    now = datetime.now(UTC) + timedelta(seconds=created_offset)
    return WhatsAppChannelConfigurationModel(
        id=uuid4(),
        organization_id=organization_id,
        bot_id=bot_id,
        display_name=f"Channel {phone_number_id}",
        phone_number_id=phone_number_id,
        whatsapp_business_account_id=f"waba-{phone_number_id}",
        public_webhook_id=uuid4(),
        status=status,
        webhook_enabled=True,
        verify_token_ciphertext="encrypted",
        app_secret_ciphertext="encrypted",
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def knowledge(
    organization_id: UUID,
    bot_id: UUID,
    status: str,
    title: str,
) -> KnowledgeEntryModel:
    now = datetime.now(UTC)
    return KnowledgeEntryModel(
        id=uuid4(),
        organization_id=organization_id,
        bot_id=bot_id,
        title=title,
        content=title,
        status=status,
        source_type="manual",
        metadata_data={},
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_sql_repository_filters_and_paginates_in_database() -> None:
    session = make_session()
    repository = SqlAlchemyWhatsAppConfigurationRepository(session)
    organization_id = uuid4()
    bot_id = uuid4()
    repository.add(
        configuration(
            organization_id,
            bot_id,
            phone_number_id="phone-1",
            status="draft",
            created_offset=1,
        ),
    )
    repository.add(
        configuration(
            organization_id,
            bot_id,
            phone_number_id="phone-2",
            status="draft",
            created_offset=2,
        ),
    )
    repository.add(
        configuration(
            uuid4(),
            bot_id,
            phone_number_id="phone-3",
            status="draft",
        ),
    )
    session.commit()

    page = repository.list_scoped(
        organization_id,
        bot_id,
        status="draft",
        phone_number_id=None,
        search="Channel",
        offset=1,
        limit=1,
    )

    assert [item.phone_number_id for item in page] == ["phone-2"]
    assert (
        repository.count_scoped(
            organization_id,
            bot_id,
            status="draft",
            phone_number_id=None,
            search="Channel",
        )
        == 2
    )
    session.close()


def test_resolver_context_drives_published_bot_knowledge() -> None:
    session = make_session()
    configuration_repository = SqlAlchemyWhatsAppConfigurationRepository(session)
    knowledge_repository = SqlAlchemyKnowledgeEntryRepository(session)
    organization_id = uuid4()
    bot_id = uuid4()
    other_bot_id = uuid4()
    active = configuration(
        organization_id,
        bot_id,
        phone_number_id="phone-active",
        status="active",
    )
    configuration_repository.add(active)
    knowledge_repository.add(
        knowledge(organization_id, bot_id, "published", "Visible"),
    )
    knowledge_repository.add(knowledge(organization_id, bot_id, "draft", "Draft"))
    knowledge_repository.add(
        knowledge(organization_id, bot_id, "archived", "Archived"),
    )
    knowledge_repository.add(
        knowledge(organization_id, other_bot_id, "published", "Other bot"),
    )
    knowledge_repository.add(
        knowledge(uuid4(), bot_id, "published", "Other tenant"),
    )
    session.commit()

    context = WhatsAppChannelResolver(configuration_repository).resolve(
        "phone-active",
    )
    entries = BotKnowledgeProvider(knowledge_repository).retrieve_published(
        context.organization_id,
        context.bot_id,
    )

    assert context.channel_type == "whatsapp"
    assert context.channel_configuration_id == active.id
    assert [entry.title for entry in entries] == ["Visible"]
    session.close()
