import base64
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.application.channel.messaging import ChannelMessageHandler
from app.application.whatsapp_configuration.resolver import (
    WhatsAppChannelResolver,
)
from app.application.whatsapp_live.processor import (
    WhatsAppLiveMessageProcessor,
    WhatsAppRuntimeRoutingError,
)
from app.application.whatsapp_live.sender import WhatsAppChannelMessageSender
from app.channels.whatsapp.live_mapper import WhatsAppInboundMessageMapper
from app.domain.channel.contracts import (
    InboundChannelMessage,
    OutboundChannelMessage,
)
from app.domain.whatsapp_live.contracts import (
    WhatsAppInboundCandidate,
    WhatsAppParsedWebhook,
    WhatsAppStatusEvent,
)
from app.infrastructure.database import Base
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    InMemoryWhatsAppConfigurationRepository,
)
from app.infrastructure.repositories.whatsapp_message_transport_repository import (
    InMemoryInboundMessageReceiptRepository,
    InMemoryOutboundMessageAttemptRepository,
    SqlAlchemyInboundMessageReceiptRepository,
    SqlAlchemyOutboundMessageAttemptRepository,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


class RecordingHandler(ChannelMessageHandler):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[InboundChannelMessage] = []

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("controlled core failure")
        return OutboundChannelMessage(
            channel_type=message.channel_type,
            external_recipient_id=message.external_sender_id,
            text="Respuesta del Core",
            reply_to_external_message_id=message.external_message_id,
        )


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def cipher() -> EnvironmentSecretCipher:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("ascii")
    return EnvironmentSecretCipher(key)


def configuration(
    secret_cipher: EnvironmentSecretCipher,
    *,
    phone_number_id: str = "123456789",
) -> WhatsAppChannelConfigurationModel:
    return WhatsAppChannelConfigurationModel(
        id=uuid4(),
        organization_id=uuid4(),
        bot_id=uuid4(),
        display_name="Support",
        phone_number_id=phone_number_id,
        whatsapp_business_account_id=f"waba-{phone_number_id}",
        public_webhook_id=uuid4(),
        status="active",
        webhook_enabled=True,
        verify_token_ciphertext=secret_cipher.encrypt("verify-token"),
        access_token_ciphertext=secret_cipher.encrypt("access-token"),
        app_secret_ciphertext=secret_cipher.encrypt("app-secret"),
        created_by_user_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )


def parsed(
    phone_number_id: str = "123456789",
    message_id: str = "wamid.1",
) -> WhatsAppParsedWebhook:
    return WhatsAppParsedWebhook(
        messages=(
            WhatsAppInboundCandidate(
                external_message_id=message_id,
                external_sender_id="51999999999",
                phone_number_id=phone_number_id,
                timestamp=NOW,
                message_type="text",
                text="Necesito soporte",
            ),
        )
    )


def build_processor(
    session: Session,
    *,
    client: FakeWhatsAppCloudApiClient | None = None,
    handler: RecordingHandler | None = None,
    outbound_enabled: bool = True,
    outbound_recipient_allowlist: frozenset[str] | None = None,
) -> tuple[
    WhatsAppLiveMessageProcessor,
    WhatsAppChannelConfigurationModel,
    InMemoryInboundMessageReceiptRepository,
    InMemoryOutboundMessageAttemptRepository,
    FakeWhatsAppCloudApiClient,
    RecordingHandler,
]:
    secret_cipher = cipher()
    model = configuration(secret_cipher)
    configurations = InMemoryWhatsAppConfigurationRepository()
    configurations.add(model)
    receipts = InMemoryInboundMessageReceiptRepository()
    outbound = InMemoryOutboundMessageAttemptRepository()
    fake_client = client or FakeWhatsAppCloudApiClient()
    recording_handler = handler or RecordingHandler()
    sender = WhatsAppChannelMessageSender(
        configurations,
        secret_cipher,
        fake_client,
        max_text_chars=4096,
    )
    processor = WhatsAppLiveMessageProcessor(
        configuration_repository=configurations,
        receipt_repository=receipts,
        outbound_repository=outbound,
        resolver=WhatsAppChannelResolver(configurations),
        mapper=WhatsAppInboundMessageMapper(),
        handler=recording_handler,
        sender=sender,
        secret_cipher=secret_cipher,
        session=session,
        max_text_chars=4096,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=60,
        outbound_enabled=outbound_enabled,
        outbound_recipient_allowlist=outbound_recipient_allowlist,
        now=lambda: NOW,
    )
    return (
        processor,
        model,
        receipts,
        outbound,
        fake_client,
        recording_handler,
    )


async def test_processor_processes_inbound_when_outbound_is_disabled(
    session: Session,
) -> None:
    processor, model, receipts, outbound, client, handler = build_processor(
        session,
        outbound_enabled=False,
    )

    result = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert result[0].status == "processed"
    assert len(handler.messages) == 1
    assert client.calls == []
    assert outbound.attempts == {}
    receipt = receipts.get_by_external_message_id("whatsapp", "wamid.1")
    assert receipt is not None
    assert receipt.status == "processed"


async def test_processor_suppresses_outbound_for_recipient_outside_allowlist(
    session: Session,
) -> None:
    processor, model, receipts, outbound, client, handler = build_processor(
        session,
        outbound_recipient_allowlist=frozenset({"51911111111"}),
    )

    result = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert result[0].status == "processed"
    assert len(handler.messages) == 1
    assert client.calls == []
    assert outbound.attempts == {}


async def test_processor_sends_outbound_for_allowlisted_recipient(
    session: Session,
) -> None:
    processor, model, _, outbound, client, _ = build_processor(
        session,
        outbound_recipient_allowlist=frozenset({"51999999999"}),
    )

    result = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert result[0].status == "processed"
    assert len(client.calls) == 1
    assert len(outbound.attempts) == 1


async def test_processor_is_idempotent_and_persists_provider_status(
    session: Session,
) -> None:
    processor, model, receipts, outbound, client, handler = build_processor(session)

    first = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )
    duplicate = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert first[0].status == "processed"
    assert duplicate[0].status == "duplicate"
    assert len(handler.messages) == 1
    assert len(client.calls) == 1
    receipt = receipts.get_by_external_message_id("whatsapp", "wamid.1")
    assert receipt is not None
    assert receipt.status == "processed"
    assert receipt.attempt_count == 1
    assert len(outbound.attempts) == 1
    attempt = next(iter(outbound.attempts.values()))
    assert attempt.status == "sent"
    assert attempt.provider_message_id is not None
    assert "51999999999" not in repr(attempt)
    assert "Respuesta del Core" not in repr(attempt)

    delivered = WhatsAppParsedWebhook(
        statuses=(
            WhatsAppStatusEvent(
                provider_message_id=attempt.provider_message_id,
                phone_number_id=model.phone_number_id,
                status="delivered",
                timestamp=NOW + timedelta(minutes=1),
            ),
        )
    )
    await processor.process(
        delivered,
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )
    assert attempt.status == "delivered"

    older = delivered.model_copy(
        update={
            "statuses": (
                delivered.statuses[0].model_copy(
                    update={
                        "status": "sent",
                        "timestamp": NOW,
                    }
                ),
            )
        }
    )
    await processor.process(
        older,
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )
    assert attempt.status == "delivered"


async def test_retryable_failure_is_scheduled_and_service_can_retry(
    session: Session,
) -> None:
    client = FakeWhatsAppCloudApiClient(("429", "success"))
    processor, model, _, outbound, _, handler = build_processor(
        session,
        client=client,
    )

    result = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )
    attempt = outbound.attempts[result[0].outbound_attempt_ids[0]]

    assert result[0].status == "processed"
    assert len(handler.messages) == 1
    assert attempt.status == "pending"
    assert attempt.attempt_count == 1
    assert attempt.last_error_code == "RATE_LIMITED"
    assert attempt.next_attempt_at == NOW + timedelta(seconds=1)

    attempt.next_attempt_at = NOW - timedelta(seconds=1)
    assert await processor.retry_attempt(attempt.id)
    assert attempt.status == "sent"
    assert attempt.attempt_count == 2
    assert len(client.calls) == 2


async def test_core_failure_marks_receipt_failed_without_outbound(
    session: Session,
) -> None:
    processor, model, receipts, outbound, client, handler = build_processor(
        session,
        handler=RecordingHandler(fail=True),
    )

    result = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert result[0].status == "failed"
    receipt = receipts.get_by_external_message_id("whatsapp", "wamid.1")
    assert receipt is not None
    assert receipt.status == "failed"
    assert receipt.last_error_code == "PROCESSING_FAILED"
    assert len(handler.messages) == 1
    assert outbound.attempts == {}
    assert client.calls == []

    duplicate = await processor.process(
        parsed(),
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )
    assert duplicate[0].status == "duplicate"
    assert len(handler.messages) == 1


async def test_non_text_event_is_ignored_without_transport_records(
    session: Session,
) -> None:
    processor, model, receipts, outbound, client, handler = build_processor(session)
    unsupported = WhatsAppParsedWebhook(
        messages=(
            WhatsAppInboundCandidate(
                external_message_id="wamid.image",
                external_sender_id="51999999999",
                phone_number_id=model.phone_number_id,
                timestamp=NOW,
                message_type="image",
            ),
        )
    )

    result = await processor.process(
        unsupported,
        public_webhook_id=model.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert result[0].status == "ignored"
    assert receipts.receipts == {}
    assert outbound.attempts == {}
    assert client.calls == []
    assert handler.messages == []


async def test_processor_rejects_unknown_or_cross_configuration_identity(
    session: Session,
) -> None:
    processor, model, _, outbound, _, _ = build_processor(session)

    with pytest.raises(WhatsAppRuntimeRoutingError):
        await processor.process(
            parsed(phone_number_id="999999999"),
            public_webhook_id=model.public_webhook_id,
            correlation_id=uuid4(),
        )

    other_cipher = cipher()
    other = configuration(other_cipher, phone_number_id="987654321")
    foreign_attempt = OutboundMessageAttemptModel(
        id=uuid4(),
        organization_id=other.organization_id,
        bot_id=other.bot_id,
        channel_configuration_id=other.id,
        external_recipient_hash="x" * 64,
        external_recipient_ciphertext=other_cipher.encrypt("51999999999"),
        message_ciphertext=other_cipher.encrypt("response"),
        status="sent",
        provider_message_id="provider.foreign",
        created_at=NOW,
        updated_at=NOW,
        sent_at=NOW,
        provider_status_updated_at=NOW,
    )
    outbound.create_pending(foreign_attempt)
    foreign_status = WhatsAppParsedWebhook(
        statuses=(
            WhatsAppStatusEvent(
                provider_message_id="provider.foreign",
                phone_number_id=model.phone_number_id,
                status="delivered",
                timestamp=NOW + timedelta(seconds=1),
            ),
        )
    )

    with pytest.raises(WhatsAppRuntimeRoutingError):
        await processor.process(
            foreign_status,
            public_webhook_id=model.public_webhook_id,
            correlation_id=uuid4(),
        )
    assert foreign_attempt.status == "sent"


def test_sql_repositories_enforce_idempotency_locking_and_status_order(
    session: Session,
) -> None:
    receipt_repository = SqlAlchemyInboundMessageReceiptRepository(session)
    outbound_repository = SqlAlchemyOutboundMessageAttemptRepository(session)
    organization_id = uuid4()
    bot_id = uuid4()
    configuration_id = uuid4()
    receipt = InboundMessageReceiptModel(
        id=uuid4(),
        channel_type="whatsapp",
        external_message_id="wamid.sql",
        organization_id=organization_id,
        bot_id=bot_id,
        channel_configuration_id=configuration_id,
        status="received",
        received_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )

    created, is_new = receipt_repository.create_or_get(receipt)
    session.commit()
    duplicate, duplicate_is_new = receipt_repository.create_or_get(
        InboundMessageReceiptModel(
            id=uuid4(),
            channel_type="whatsapp",
            external_message_id="wamid.sql",
            organization_id=organization_id,
            bot_id=bot_id,
            channel_configuration_id=configuration_id,
            status="received",
            received_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    assert is_new
    assert not duplicate_is_new
    assert duplicate.id == created.id
    assert receipt_repository.acquire_for_processing(created.id)
    assert not receipt_repository.acquire_for_processing(created.id)
    receipt_repository.mark_processed(created.id, NOW)

    attempt = OutboundMessageAttemptModel(
        id=uuid4(),
        inbound_receipt_id=created.id,
        organization_id=organization_id,
        bot_id=bot_id,
        channel_configuration_id=configuration_id,
        external_recipient_hash="h" * 64,
        external_recipient_ciphertext="cipher-recipient",
        message_ciphertext="cipher-message",
        status="pending",
        created_at=NOW,
        updated_at=NOW,
    )
    outbound_repository.create_pending(attempt)
    outbound_repository.mark_attempt_started(attempt.id)
    outbound_repository.mark_sent(attempt.id, "provider.sql", NOW)
    session.commit()

    assert outbound_repository.update_provider_status(
        "provider.sql",
        "read",
        NOW + timedelta(minutes=2),
        None,
    )
    assert not outbound_repository.update_provider_status(
        "provider.sql",
        "failed",
        NOW + timedelta(minutes=3),
        "LATE_FAILURE",
    )
    assert not outbound_repository.update_provider_status(
        "provider.sql",
        "delivered",
        NOW + timedelta(minutes=1),
        None,
    )
    session.commit()
    assert attempt.status == "read"
    assert attempt.last_error_code is None
