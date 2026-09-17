"""Regressions through the actual product composition, without external providers."""

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.conversation_management.history import (
    ManagedConversationHistoryLoader,
)
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.knowledge_management.retriever import (
    PublishedBotKnowledgeRetriever,
)
from app.core.automation.service import AutomationService
from app.domain.channel.contracts import ResolvedChannelContext
from app.domain.conversation.contracts import ConversationMessage
from app.domain.knowledge.contracts import KnowledgeQuery
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_event import BusinessEventModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.knowledge_catalog_entry import KnowledgeCatalogEntryModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
from app.infrastructure.settings import Settings
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests.test_whatsapp_live_processor_repository import cipher, configuration, parsed


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Generator[Session]:
    # Core background automation is a separate responsibility; never start threads
    # against the machine's configured DB from a composition regression.
    monkeypatch.setattr(AutomationService, "execute", lambda *args, **kwargs: uuid4())

    def unexpected_recovery(*args: object, **kwargs: object) -> int:
        raise AssertionError("Request composition must not perform global recovery")

    monkeypatch.setattr(AutomationService, "recover", unexpected_recovery)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        yield db
    engine.dispose()


def seed_channel(session: Session, phone: str) -> WhatsAppChannelConfigurationModel:
    model = configuration(cipher(), phone_number_id=phone)
    session.add(OrganizationModel(id=model.organization_id, name="Audit", slug=phone))
    session.add(
        BotModel(
            id=model.bot_id,
            organization_id=model.organization_id,
            name="Audit",
            slug=phone,
            status="active",
        )
    )
    session.add(model)
    session.commit()
    return model


def seed_knowledge(
    session: Session,
    model: WhatsAppChannelConfigurationModel,
    content: str,
    status: str = "published",
) -> None:
    session.add(
        KnowledgeEntryModel(
            id=uuid4(),
            organization_id=model.organization_id,
            bot_id=model.bot_id,
            title="Horario",
            content=content,
            status=status,
            created_by_user_id=model.created_by_user_id,
        )
    )
    session.commit()


def settings(*, mode: str = "fake", recipients: tuple[str, ...] = ()) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        use_database=True,
        contact_identity_hmac_key="audit-test-identity-key-at-least-32-characters",
        whatsapp_live_client_mode=mode,
        whatsapp_outbound_allowed_recipients=recipients,
    )


async def ask(
    session: Session, model: WhatsAppChannelConfigurationModel, message_id: str
) -> str:
    processor = get_whatsapp_live_message_processor(
        session, cipher(), FakeWhatsAppCloudApiClient(), settings()
    )
    payload = parsed(model.phone_number_id, message_id)
    payload = payload.model_copy(
        update={
            "messages": (
                payload.messages[0].model_copy(update={"text": "¿Cuál es el horario?"}),
            )
        }
    )
    result = await processor.process(
        payload, public_webhook_id=model.public_webhook_id, correlation_id=uuid4()
    )
    assert result[0].status == "processed"
    attempt = session.get(
        OutboundMessageAttemptModel, result[0].outbound_attempt_ids[0]
    )
    assert attempt is not None
    return cipher().decrypt(attempt.message_ciphertext)


async def test_published_knowledge_drives_scoped_response_and_state_survives_close(
    session: Session,
) -> None:
    first = seed_channel(session, "123456789")
    second = seed_channel(session, "987654321")
    seed_knowledge(session, first, "Abrimos solo domingos de 14:00 a 16:00.")
    seed_knowledge(session, second, "Abrimos solo martes de 10:00 a 12:00.")
    seed_knowledge(session, first, "Horario privado del borrador.", "draft")
    # A contradictory legacy entry must never influence the product response.
    session.add(
        KnowledgeCatalogEntryModel(
            source_id="seed",
            keywords="horario",
            content="Lunes a viernes de 9 a 18.",
            confidence="high",
        )
    )
    session.commit()
    assert (
        await ask(session, first, "audit.first")
        == "Abrimos solo domingos de 14:00 a 16:00."
    )
    assert (
        await ask(session, second, "audit.second")
        == "Abrimos solo martes de 10:00 a 12:00."
    )
    first_id = first.organization_id
    session.close()
    rows = session.scalars(select(ConversationModel)).all()
    assert len(rows) == 2
    assert all(row.status == "in_progress" for row in rows)
    assert session.scalars(select(BusinessEventModel)).first() is not None
    records = session.scalars(
        select(MessageModel).where(MessageModel.organization_id == first_id)
    ).all()
    assert len(records) == 2
    assert all(record.content == "" and record.text_ciphertext for record in records)


async def test_no_published_match_does_not_use_legacy_seed(session: Session) -> None:
    model = seed_channel(session, "123456789")
    seed_knowledge(session, model, "Abrimos todos los domingos.", "archived")
    response = await ask(session, model, "audit.no-match")
    assert "domingos" not in response
    assert "lunes" not in response
    assert response


def test_retriever_rejects_other_organization(session: Session) -> None:
    model = seed_channel(session, "123456789")
    retriever = PublishedBotKnowledgeRetriever(
        BotKnowledgeProvider(SqlAlchemyKnowledgeEntryRepository(session)),
        model.organization_id,
        model.bot_id,
    )
    with pytest.raises(ValueError, match="scope mismatch"):
        retriever.retrieve(
            KnowledgeQuery(
                content="horario", intent="question", company_id=str(uuid4())
            )
        )


@pytest.mark.parametrize("path", ["bot", "human", "retry"])
async def test_meta_allowlist_blocks_every_delivery_path(
    session: Session, path: str
) -> None:
    model = seed_channel(session, "123456789")
    client = FakeWhatsAppCloudApiClient()
    processor = get_whatsapp_live_message_processor(
        session, cipher(), client, settings(mode="meta")
    )
    if path == "bot":
        result = await processor.process(
            parsed(model.phone_number_id),
            public_webhook_id=model.public_webhook_id,
            correlation_id=uuid4(),
        )
        assert result[0].status == "processed"
        assert result[0].outbound_attempt_ids == ()
        assert client.calls == []
        return
    elif path == "human":
        conversation_id = uuid4()
        session.add(
            ConversationModel(
                id=conversation_id,
                company_id=str(model.organization_id),
                customer_id="51999999999",
                organization_id=model.organization_id,
                bot_id=model.bot_id,
                channel_configuration_id=model.id,
                channel="whatsapp",
                status="in_progress",
                management_status="open",
                started_at=datetime.now(UTC),
            )
        )
        session.commit()
        human_attempt = await processor.send_human_reply(
            conversation_id=conversation_id,
            organization_id=model.organization_id,
            bot_id=model.bot_id,
            channel_configuration_id=model.id,
            recipient_id="51999999999",
            text="Audit human reply",
            idempotency_key="audit-human",
            author_user_id=model.created_by_user_id,
        )
        attempt_id = human_attempt.id
    else:
        attempt_id = uuid4()
        session.add(
            OutboundMessageAttemptModel(
                id=attempt_id,
                organization_id=model.organization_id,
                bot_id=model.bot_id,
                channel_configuration_id=model.id,
                external_recipient_hash="synthetic",
                external_recipient_ciphertext=cipher().encrypt("51999999999"),
                message_ciphertext=cipher().encrypt("Audit pending reply"),
                status="pending",
                attempt_count=0,
                next_attempt_at=None,
            )
        )
        session.commit()
        assert await processor.retry_attempt(attempt_id)
    attempt = session.get(OutboundMessageAttemptModel, attempt_id)
    assert attempt is not None
    assert attempt.status == "failed"
    assert attempt.last_error_code == "RECIPIENT_NOT_ALLOWED"
    assert client.calls == []


async def test_meta_allowlisted_recipient_is_delivered(session: Session) -> None:
    model = seed_channel(session, "123456789")
    client = FakeWhatsAppCloudApiClient()
    processor = get_whatsapp_live_message_processor(
        session, cipher(), client, settings(mode="meta", recipients=("51999999999",))
    )
    result = await processor.process(
        parsed(model.phone_number_id),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )
    assert result[0].status == "processed"
    assert len(client.calls) == 1


def test_recipient_csv_setting() -> None:
    value = settings().model_dump()
    value["whatsapp_outbound_allowed_recipients"] = "51999999999, 51911111111"
    parsed_settings = Settings(_env_file=None, **value)
    assert parsed_settings.whatsapp_outbound_allowed_recipients == (
        "51999999999",
        "51911111111",
    )


async def test_managed_history_decrypts_previous_messages_only(
    session: Session,
) -> None:
    model = seed_channel(session, "123456789")
    seed_knowledge(session, model, "Abrimos domingos.")
    await ask(session, model, "history.previous")
    await ask(session, model, "history.current")
    conversation = session.scalars(select(ConversationModel)).one()
    scope = ResolvedChannelContext(
        channel_type="whatsapp",
        organization_id=model.organization_id,
        bot_id=model.bot_id,
        channel_configuration_id=model.id,
        external_channel_id=model.phone_number_id,
    )
    message = ConversationMessage(
        content="Pregunta actual",
        customer_id="synthetic",
        company_id=str(model.organization_id),
        conversation_id=conversation.id,
        metadata={"external_message_id": "history.current"},
    )
    loader = ManagedConversationHistoryLoader(session, cipher(), scope)
    history = loader(message)
    assert [entry.content for entry in history].count("¿Cuál es el horario?") == 1
    assert "Abrimos domingos." in [entry.content for entry in history]
    assert all(row.content == "" for row in session.scalars(select(MessageModel)))
    with pytest.raises(ValueError, match="scope mismatch"):
        loader(message.model_copy(update={"company_id": str(uuid4())}))
    # Even records with the same conversation id cannot cross a bot boundary.
    session.add(
        MessageModel(
            conversation_id=conversation.id,
            organization_id=model.organization_id,
            bot_id=uuid4(),
            role="user",
            content="",
            text_ciphertext=cipher().encrypt("Other bot private data"),
            occurred_at=datetime.now(UTC),
        )
    )
    session.commit()
    assert "Other bot private data" not in [entry.content for entry in loader(message)]
    for index in range(8):
        session.add(
            MessageModel(
                conversation_id=conversation.id,
                organization_id=model.organization_id,
                bot_id=model.bot_id,
                role="user",
                content="",
                text_ciphertext=cipher().encrypt(str(index) * 5000),
                occurred_at=datetime.now(UTC),
            )
        )
    session.commit()
    bounded = loader(message)
    assert sum(len(entry.content) for entry in bounded) == 16000
    assert all(len(entry.content) <= 4000 for entry in bounded)


def test_knowledge_isolated_between_bots_of_same_organization(session: Session) -> None:
    model = seed_channel(session, "123456789")
    seed_knowledge(session, model, "Horario de mi bot.")
    session.add(
        KnowledgeEntryModel(
            id=uuid4(),
            organization_id=model.organization_id,
            bot_id=uuid4(),
            title="Horario",
            content="Horario de otro bot.",
            status="published",
            created_by_user_id=model.created_by_user_id,
        )
    )
    session.commit()
    retriever = PublishedBotKnowledgeRetriever(
        BotKnowledgeProvider(SqlAlchemyKnowledgeEntryRepository(session)),
        model.organization_id,
        model.bot_id,
    )
    result = retriever.retrieve(
        KnowledgeQuery(
            content="horario",
            intent="question",
            company_id=str(model.organization_id),
        )
    )
    assert [item.content for item in result] == ["Horario de mi bot."]
