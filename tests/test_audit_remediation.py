"""Regression scenarios from the September audit, using synthetic data only."""

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.api.dependencies import get_password_service
from app.api.public_contacts_routes import Registration, register_contact
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.channel.messaging import ChannelMessageHandler
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.knowledge_management.retriever import (
    PublishedBotKnowledgeRetriever,
)
from app.application.whatsapp_live.sender import WhatsAppChannelDeliveryError
from app.core.conversation.router import MessageRouter
from app.domain.channel.contracts import InboundChannelMessage, OutboundChannelMessage
from app.domain.contacts.crm_contracts import CustomerUpdate
from app.domain.conversation.contracts import (
    ConversationContext,
    ConversationMessage,
    HistoryEntry,
)
from app.domain.knowledge.contracts import KnowledgeQuery
from app.domain.user.contracts import UserCreate
from app.infrastructure.database import Base
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel as Inbox,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel as Outbox,
)
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
from app.infrastructure.settings import Settings, get_settings
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations.whatsapp_worker import recover_batch
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tests.test_crm import crm as crm
from tests.test_luri_stabilization import seed_channel, seed_knowledge, settings
from tests.test_whatsapp_live_processor_repository import (
    build_processor,
    cipher,
    parsed,
)


@pytest.fixture
def db() -> Generator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


class FailAfterWork(ChannelMessageHandler):
    def __init__(self, inner: ChannelMessageHandler) -> None:
        self.inner = inner
        self.fail = True

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        result = self.inner.handle(message)
        if self.fail:
            raise RuntimeError("synthetic crash after business changes")
        return result


async def test_failed_work_rolls_back_and_worker_recovers_original_payload(
    db: Session,
) -> None:
    channel = seed_channel(db, "123456789")
    seed_knowledge(db, channel, "Abrimos solo domingos de 14:00 a 16:00.")
    client = FakeWhatsAppCloudApiClient()
    processor = get_whatsapp_live_message_processor(db, cipher(), client, settings())
    wrapper = FailAfterWork(processor._handler)
    processor._handler = wrapper
    payload = parsed(channel.phone_number_id, "audit.recovery")
    result = await processor.process(
        payload, public_webhook_id=channel.public_webhook_id, correlation_id=uuid4()
    )
    assert result[0].status == "failed"
    assert db.scalar(select(func.count()).select_from(ContactModel)) == 0
    assert db.scalar(select(func.count()).select_from(MessageModel)) == 0
    receipt = db.get(Inbox, result[0].receipt_id)
    assert receipt is not None and receipt.payload_ciphertext
    assert payload.messages[0].text is not None
    assert payload.messages[0].text not in receipt.payload_ciphertext
    assert not client.calls
    wrapper.fail = False
    future = datetime.now(UTC) + timedelta(minutes=2)
    processor._now = lambda: future
    await recover_batch(db, processor, cipher(), now=future)
    db.expire_all()
    assert receipt.status == "processed" and receipt.payload_ciphertext is None
    assert db.scalar(select(func.count()).select_from(ContactModel)) == 1
    assert db.scalar(select(func.count()).select_from(MessageModel)) == 2
    assert len(client.calls) == 1
    again = await processor.process(
        payload, public_webhook_id=channel.public_webhook_id, correlation_id=uuid4()
    )
    assert again[0].status == "duplicate" and len(client.calls) == 1


async def test_outbox_recovers_without_repeating_handler(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = seed_channel(db, "123456789")
    client = FakeWhatsAppCloudApiClient()
    processor = get_whatsapp_live_message_processor(db, cipher(), client, settings())
    send = processor._sender.send

    async def unavailable(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise WhatsAppChannelDeliveryError("RATE_LIMITED", retryable=True)

    monkeypatch.setattr(processor._sender, "send", unavailable)
    result = await processor.process(
        parsed(), public_webhook_id=channel.public_webhook_id, correlation_id=uuid4()
    )
    assert result[0].status == "processed"
    assert not client.calls
    count = db.scalar(select(func.count()).select_from(MessageModel))
    monkeypatch.setattr(processor._sender, "send", send)
    monkeypatch.setattr(
        processor._handler,
        "handle",
        Mock(side_effect=AssertionError("must not replay business work")),
    )
    future = datetime.now(UTC) + timedelta(minutes=2)
    processor._now = lambda: future
    await recover_batch(db, processor, cipher(), now=future)
    assert len(client.calls) == 1
    assert db.scalar(select(func.count()).select_from(MessageModel)) == count
    assert db.scalars(select(Outbox)).one().status == "sent"


async def test_concurrent_retries_have_one_owner(db: Session) -> None:
    processor, channel, _, outbox, client, _ = build_processor(db)
    await processor.process(
        parsed(), public_webhook_id=channel.public_webhook_id, correlation_id=uuid4()
    )
    attempt = next(iter(outbox.attempts.values()))
    attempt.status, attempt.attempt_count, attempt.next_attempt_at = "pending", 0, None
    send = processor._sender.send

    async def slow(*args, **kwargs):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.02)
        return await send(*args, **kwargs)

    processor._sender.send = slow  # type: ignore[method-assign]
    before = len(client.calls)
    results = await asyncio.gather(
        processor.retry_attempt(attempt.id), processor.retry_attempt(attempt.id)
    )
    assert sorted(results) == [False, True]
    assert len(client.calls) == before + 1


async def test_expired_delivery_is_not_blindly_resent(db: Session) -> None:
    channel = seed_channel(db, "123456789")
    client = FakeWhatsAppCloudApiClient()
    processor = get_whatsapp_live_message_processor(db, cipher(), client, settings())
    await processor.process(
        parsed(), public_webhook_id=channel.public_webhook_id, correlation_id=uuid4()
    )
    attempt = db.scalars(select(Outbox)).one()
    attempt.status = "pending"
    attempt.delivery_token = uuid4()
    attempt.delivery_started_at = datetime.now(UTC) - timedelta(minutes=6)
    db.commit()
    before = len(client.calls)
    await recover_batch(db, processor, cipher())
    db.refresh(attempt)
    assert attempt.status == "failed" and attempt.last_error_code == "DELIVERY_UNKNOWN"
    assert len(client.calls) == before


def test_crm_notes_preserve_new_and_legacy_registration(crm):  # type: ignore[no-untyped-def]
    _, db, actor, _, service = crm
    register_contact(
        db,
        actor.organization_id,
        Registration(
            name="Audit ficticio",
            whatsapp="+12025550148",
            consent=True,
            notice_version="contact-registration-v1",
        ),
        service.hasher,
        service.cipher,
    )
    contact = db.scalars(select(ContactModel)).one()
    evidence = contact.registration_ciphertext
    assert evidence and "contact-registration-v1" in service.cipher.decrypt(evidence)
    first = service.update(
        actor.organization_id,
        contact.id,
        actor,
        CustomerUpdate(display_name="Audit", notes="Consulta atendida", version=0),
    )
    assert (
        contact.registration_ciphertext == evidence
        and first.notes == "Consulta atendida"
    )
    # A pre-migration contact only has evidence in notes. Preserve it on edit too.
    contact.registration_ciphertext = None
    contact.notes_ciphertext = evidence
    db.commit()
    service.update(
        actor.organization_id,
        contact.id,
        actor,
        CustomerUpdate(display_name="Audit", notes="", version=first.version),
    )
    assert contact.registration_ciphertext == evidence


def test_history_reaches_business_request() -> None:
    brain = Mock()
    history = HistoryEntry(
        role="user", content="Necesito el horario", created_at=datetime.now(UTC)
    )
    MessageRouter(brain).route(
        ConversationContext(
            message=ConversationMessage(
                content="Y el domingo?", company_id=str(uuid4()), customer_id="audit"
            ),
            history=[history],
        )
    )
    assert brain.process.call_args.args[0].history == (history,)


def test_configured_password_policy_and_cached_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTWA_AUTH_PASSWORD_MAX_LENGTH", "64")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        UserCreate(
            organization_id=uuid4(), email="audit@example.test", password="x" * 65
        )
    first = get_password_service()
    assert get_password_service() is first
    monkeypatch.setenv("BOTWA_AUTH_PASSWORD_MAX_LENGTH", "512")
    get_settings.cache_clear()
    body = UserCreate(
        organization_id=uuid4(), email="audit@example.test", password="x" * 300
    )
    second = get_password_service()
    assert second is not first
    assert second.verify(body.password, second.hash(body.password))


def test_immutable_revision_overrides_stale_environment(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    from app.infrastructure import build_metadata

    path = tmp_path / "revision"
    path.write_text("a" * 40)
    monkeypatch.setattr(build_metadata, "BUILD_FILE", path)
    assert Settings(_env_file=None, build_sha="b" * 40).build_sha == "a" * 40


def test_retrieval_searches_beyond_first_hundred(db: Session) -> None:
    channel = seed_channel(db, "123456789")
    for index in range(110):
        db.add(
            KnowledgeEntryModel(
                id=uuid4(),
                organization_id=channel.organization_id,
                bot_id=channel.bot_id,
                title=f"Catalog {index}",
                content="Contenido general",
                status="published",
                created_by_user_id=channel.created_by_user_id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    db.add(
        KnowledgeEntryModel(
            id=uuid4(),
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            title="Servicio de astronomía",
            content="Disponemos de telescopios.",
            status="published",
            created_by_user_id=channel.created_by_user_id,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    db.commit()
    retriever = PublishedBotKnowledgeRetriever(
        BotKnowledgeProvider(SqlAlchemyKnowledgeEntryRepository(db)),
        channel.organization_id,
        channel.bot_id,
    )
    matches = retriever.retrieve(
        KnowledgeQuery(
            content="telescopios",
            intent="question",
            company_id=str(channel.organization_id),
        )
    )
    assert [item.content for item in matches] == ["Disponemos de telescopios."]


async def test_notification_retry_checks_tenant_and_current_policy(db: Session) -> None:
    first = seed_channel(db, "123456789")
    second = seed_channel(db, "987654321")
    recipient = "12025550148"
    config = settings()
    config.lead_notification_recipients = (recipient,)
    config.lead_notification_scopes = {
        f"{first.organization_id}:{first.bot_id}": (recipient,),
    }
    client = FakeWhatsAppCloudApiClient()
    processor = get_whatsapp_live_message_processor(db, cipher(), client, config)

    def pending(channel: WhatsAppChannelConfigurationModel) -> Outbox:
        attempt = Outbox(
            id=uuid4(),
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            channel_configuration_id=channel.id,
            external_recipient_hash="synthetic",
            external_recipient_ciphertext=cipher().encrypt(recipient),
            message_ciphertext=cipher().encrypt("Synthetic notification"),
            notification=True,
            status="pending",
            attempt_count=0,
        )
        db.add(attempt)
        db.commit()
        return attempt

    other = pending(second)
    assert await processor.retry_attempt(other.id)
    assert other.last_error_code == "NOTIFICATION_NOT_AUTHORIZED"
    assert not client.calls
    allowed = pending(first)
    assert await processor.retry_attempt(allowed.id)
    assert allowed.status == "sent" and len(client.calls) == 1
    revoked = pending(first)
    config.lead_notification_scopes = {}
    assert await processor.retry_attempt(revoked.id)
    assert revoked.last_error_code == "NOTIFICATION_NOT_AUTHORIZED"
    assert len(client.calls) == 1
