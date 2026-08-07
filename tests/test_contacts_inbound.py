import base64
import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.application.channel.conversation_handler import ChannelConversationHandler
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.application.conversation_management.managed_handler import (
    ManagedChannelConversationHandler,
)
from app.application.conversation_management.service import (
    ConversationManagementConflictError,
    ConversationManagementService,
)
from app.application.whatsapp_configuration.resolver import WhatsAppChannelResolver
from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
from app.application.whatsapp_live.sender import WhatsAppChannelMessageSender
from app.channels.whatsapp.live_mapper import WhatsAppInboundMessageMapper
from app.domain.channel.contracts import InboundChannelMessage, OutboundChannelMessage
from app.domain.contacts.contracts import (
    ContactIdentityError,
    ContactIdentityNormalizer,
)
from app.domain.whatsapp_live.contracts import (
    WhatsAppInboundCandidate,
    WhatsAppParsedWebhook,
)
from app.infrastructure import models as _models
from app.infrastructure.database import Base
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    InMemoryWhatsAppConfigurationRepository,
)
from app.infrastructure.repositories.whatsapp_message_transport_repository import (
    InMemoryInboundMessageReceiptRepository,
    InMemoryOutboundMessageAttemptRepository,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)
HMAC_KEY = "contact-test-hmac-key-with-at-least-thirty-two-characters"


class RecordingCore(ChannelConversationHandler):
    def __init__(self) -> None:
        self.calls = 0

    @staticmethod
    def conversation_id_for(message: InboundChannelMessage) -> UUID:
        return ChannelConversationHandler.conversation_id_for(message)

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        self.calls += 1
        return OutboundChannelMessage(
            channel_type=message.channel_type,
            external_recipient_id=message.external_sender_id,
            text="core response",
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


def _cipher() -> EnvironmentSecretCipher:
    return EnvironmentSecretCipher(base64.urlsafe_b64encode(b"c" * 32).decode())


def _configuration(
    cipher: EnvironmentSecretCipher,
    organization_id: UUID,
    bot_id: UUID,
    phone_number_id: str,
) -> WhatsAppChannelConfigurationModel:
    return WhatsAppChannelConfigurationModel(
        id=uuid4(),
        organization_id=organization_id,
        bot_id=bot_id,
        display_name="Support",
        phone_number_id=phone_number_id,
        whatsapp_business_account_id=f"waba-{phone_number_id}",
        public_webhook_id=uuid4(),
        status="active",
        webhook_enabled=True,
        verify_token_ciphertext=cipher.encrypt("verify"),
        access_token_ciphertext=cipher.encrypt("access"),
        app_secret_ciphertext=cipher.encrypt("app"),
        created_by_user_id=uuid4(),
        created_at=NOW,
        updated_at=NOW,
    )


def _payload(
    message_id: str, phone_number_id: str, sender: str
) -> WhatsAppParsedWebhook:
    return WhatsAppParsedWebhook(
        messages=(
            WhatsAppInboundCandidate(
                external_message_id=message_id,
                external_sender_id=sender,
                phone_number_id=phone_number_id,
                timestamp=NOW,
                message_type="text",
                text="Need help",
            ),
        )
    )


def _processor(
    session: Session,
    configurations: InMemoryWhatsAppConfigurationRepository,
) -> tuple[WhatsAppLiveMessageProcessor, RecordingCore, FakeWhatsAppCloudApiClient]:
    cipher = _cipher()
    management = ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session),
        BotRepository(session),
        cipher,
        session,
    )
    core = RecordingCore()
    contacts = ContactResolutionService(
        SqlAlchemyContactRepository(session),
        ContactIdentityHasher(HMAC_KEY, ContactIdentityNormalizer()),
        cipher,
        session,
    )
    handler = ManagedChannelConversationHandler(core, management, contacts=contacts)
    client = FakeWhatsAppCloudApiClient()
    return (
        WhatsAppLiveMessageProcessor(
            configuration_repository=configurations,
            receipt_repository=InMemoryInboundMessageReceiptRepository(),
            outbound_repository=InMemoryOutboundMessageAttemptRepository(),
            resolver=WhatsAppChannelResolver(configurations),
            mapper=WhatsAppInboundMessageMapper(),
            handler=handler,
            sender=WhatsAppChannelMessageSender(
                configurations,
                cipher,
                client,
                max_text_chars=4096,
            ),
            secret_cipher=cipher,
            session=session,
            max_text_chars=4096,
            max_attempts=3,
            retry_base_seconds=1,
            retry_max_seconds=60,
            now=lambda: NOW,
        ),
        core,
        client,
    )


async def test_inbound_creates_reuses_contact_and_preserves_receipt_idempotency(
    session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    cipher = _cipher()
    organization_id, bot_id = uuid4(), uuid4()
    configuration = _configuration(cipher, organization_id, bot_id, "123456789")
    configurations = InMemoryWhatsAppConfigurationRepository()
    configurations.add(configuration)
    processor, core, client = _processor(session, configurations)

    first = await processor.process(
        _payload("wamid.1", configuration.phone_number_id, "51999999999"),
        public_webhook_id=configuration.public_webhook_id,
        correlation_id=uuid4(),
    )
    repeated = await processor.process(
        _payload("wamid.2", configuration.phone_number_id, "51999999999"),
        public_webhook_id=configuration.public_webhook_id,
        correlation_id=uuid4(),
    )
    duplicate = await processor.process(
        _payload("wamid.2", configuration.phone_number_id, "51999999999"),
        public_webhook_id=configuration.public_webhook_id,
        correlation_id=uuid4(),
    )

    contacts = list(session.scalars(select(ContactModel)).all())
    conversations = list(session.scalars(select(ConversationModel)).all())
    assert [result.status for result in (*first, *repeated, *duplicate)] == [
        "processed",
        "processed",
        "duplicate",
    ]
    assert len(contacts) == 1
    assert len(conversations) == 1
    assert all(
        conversation.contact_id == contacts[0].id for conversation in conversations
    )
    assert core.calls == 2
    assert len(client.calls) == 2
    logs = capsys.readouterr().out
    assert "51999999999" not in logs
    assert HMAC_KEY not in logs


async def test_contact_is_scoped_to_tenant_and_reused_across_bots(
    session: Session,
) -> None:
    cipher = _cipher()
    organization_id, other_organization_id = uuid4(), uuid4()
    first = _configuration(cipher, organization_id, uuid4(), "111111111")
    second = _configuration(cipher, organization_id, uuid4(), "222222222")
    foreign = _configuration(cipher, other_organization_id, uuid4(), "333333333")
    configurations = InMemoryWhatsAppConfigurationRepository()
    for configuration in (first, second, foreign):
        configurations.add(configuration)
    processor, _, _ = _processor(session, configurations)

    for message_id, configuration in enumerate((first, second, foreign), start=1):
        await processor.process(
            _payload(
                f"wamid.{message_id}", configuration.phone_number_id, "51999999999"
            ),
            public_webhook_id=configuration.public_webhook_id,
            correlation_id=uuid4(),
        )

    contacts = list(session.scalars(select(ContactModel)).all())
    assert len(contacts) == 2
    assert len([c for c in contacts if c.organization_id == organization_id]) == 1
    assert len(list(session.scalars(select(ConversationModel)).all())) == 3


async def test_archived_contact_reactivates_and_legacy_conversation_is_linked(
    session: Session,
) -> None:
    cipher = _cipher()
    organization_id, bot_id = uuid4(), uuid4()
    configuration = _configuration(cipher, organization_id, bot_id, "123456789")
    configurations = InMemoryWhatsAppConfigurationRepository()
    configurations.add(configuration)
    processor, _, _ = _processor(session, configurations)
    sender = "51999999999"
    legacy_message = _payload("wamid.legacy", configuration.phone_number_id, sender)
    legacy_inbound = WhatsAppInboundMessageMapper().map(
        legacy_message.messages[0],
        WhatsAppChannelResolver(configurations).resolve(configuration.phone_number_id),
    )
    assert legacy_inbound is not None
    legacy_id = ChannelConversationHandler.conversation_id_for(legacy_inbound)
    session.add(
        ConversationModel(
            id=legacy_id,
            company_id=str(organization_id),
            customer_id=sender,
            organization_id=organization_id,
            bot_id=bot_id,
            channel_configuration_id=configuration.id,
            external_customer_id=sender,
            channel="whatsapp",
            status="new",
            management_status="open",
            started_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    archived = ContactModel(
        organization_id=organization_id,
        channel_type="whatsapp",
        external_identifier_hash=ContactIdentityHasher(
            HMAC_KEY, ContactIdentityNormalizer()
        )
        .identify(organization_id, "whatsapp", sender)
        .external_identifier_hash,
        external_identifier_ciphertext=cipher.encrypt(sender),
        status="archived",
    )
    session.add(archived)
    session.commit()

    await processor.process(
        legacy_message,
        public_webhook_id=configuration.public_webhook_id,
        correlation_id=uuid4(),
    )

    assert archived.status == "active"
    linked = session.get(ConversationModel, legacy_id)
    assert linked is not None
    assert linked.contact_id == archived.id


def test_cross_tenant_contact_link_is_rejected(session: Session) -> None:
    organization_id, foreign_organization_id = uuid4(), uuid4()
    foreign_contact = ContactModel(
        organization_id=foreign_organization_id,
        channel_type="whatsapp",
        external_identifier_hash="a" * 64,
        external_identifier_ciphertext="ciphertext",
    )
    session.add(foreign_contact)
    session.commit()
    management = ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session),
        BotRepository(session),
        _cipher(),
        session,
    )
    message = InboundChannelMessage(
        external_message_id="wamid.cross-tenant",
        external_sender_id="51999999999",
        external_recipient_id="51999999999",
        channel_type="whatsapp",
        text="Need help",
        timestamp=NOW,
        resolved_context={
            "channel_type": "whatsapp",
            "organization_id": organization_id,
            "bot_id": uuid4(),
            "channel_configuration_id": uuid4(),
            "external_channel_id": "123456789",
        },
    )

    with pytest.raises(ConversationManagementConflictError):
        management.record_inbound(message, uuid4(), uuid4(), foreign_contact.id)


def test_invalid_hmac_configuration_and_identifier_are_safe() -> None:
    with pytest.raises(ContactIdentityError) as missing:
        ContactIdentityHasher("   ", ContactIdentityNormalizer())
    with pytest.raises(ContactIdentityError) as invalid:
        ContactIdentityNormalizer().normalize("whatsapp", "secret-name-51999999999")

    assert "secret" not in str(missing.value)
    assert "51999999999" not in str(invalid.value)


def test_postgresql_contact_creation_race_creates_one_contact() -> None:
    root_url = make_url(
        os.getenv(
            "BOTWA_TEST_DATABASE_URL",
            "postgresql+psycopg://botwa:botwa@localhost:5432/postgres",
        )
    )
    if root_url.get_backend_name() != "postgresql":
        pytest.skip("Contact race validation requires PostgreSQL")
    database_name = f"botwa_prd011_contact_race_{uuid4().hex}"
    admin = create_engine(root_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is unavailable: {exc}")
    finally:
        admin.dispose()

    database_url: URL = root_url.set(database=database_name)
    engine = create_engine(database_url)
    try:
        assert _models.ContactModel is ContactModel
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        organization_id = uuid4()
        with factory.begin() as db:
            db.add(
                OrganizationModel(
                    id=organization_id,
                    name="Race tenant",
                    slug=f"race-{organization_id.hex[:12]}",
                    status="active",
                )
            )

        def resolve() -> UUID:
            with factory() as db:
                return (
                    ContactResolutionService(
                        SqlAlchemyContactRepository(db),
                        ContactIdentityHasher(HMAC_KEY, ContactIdentityNormalizer()),
                        _cipher(),
                        db,
                    )
                    .resolve(organization_id, "whatsapp", "51999999999")
                    .id
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            contact_ids = list(executor.map(lambda _: resolve(), range(2)))

        assert len(set(contact_ids)) == 1
        with factory() as db:
            assert len(list(db.scalars(select(ContactModel)).all())) == 1
    finally:
        engine.dispose()
        admin = create_engine(root_url, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database AND pid <> pg_backend_pid()"
                    ),
                    {"database": database_name},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        finally:
            admin.dispose()
