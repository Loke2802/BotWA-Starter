import base64
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.application.conversation_management.service import (
    ConversationManagementConflictError,
    ConversationManagementService,
)
from app.domain.access.contracts import Role
from app.domain.channel.contracts import (
    InboundChannelMessage,
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.analytics import ConversationManagementEventModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def cipher() -> EnvironmentSecretCipher:
    return EnvironmentSecretCipher(base64.urlsafe_b64encode(b"c" * 32).decode("ascii"))


def service(
    session: Session, organization_id: UUID, bot_id: UUID
) -> ConversationManagementService:
    session.add(
        OrganizationModel(
            id=organization_id,
            name="Org",
            slug=str(organization_id)[:12],
            status="active",
        )
    )
    session.add(
        BotModel(
            id=bot_id,
            organization_id=organization_id,
            name="Bot",
            slug="bot",
            status="active",
        )
    )
    session.commit()
    return ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session),
        BotRepository(session),
        cipher(),
        session,
    )


def actor(
    organization_id: UUID,
    role: Role = "organization_owner",
) -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"{uuid4()}@example.com",
        role=role,
    )


def inbound(
    organization_id: UUID,
    bot_id: UUID,
    *,
    sender: str = "51999999999",
    message_id: str = "wamid.1",
) -> InboundChannelMessage:
    context = ResolvedChannelContext(
        channel_type="whatsapp",
        organization_id=organization_id,
        bot_id=bot_id,
        channel_configuration_id=uuid4(),
        external_channel_id="123456789",
    )
    return InboundChannelMessage(
        channel_type="whatsapp",
        external_message_id=message_id,
        external_sender_id=sender,
        external_recipient_id="123456789",
        text="Contenido sensible",
        timestamp=NOW,
        resolved_context=context,
    )


def test_records_encrypted_messages_with_scoped_deduplication_and_lifecycle(
    session: Session,
) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    message = inbound(organization_id, bot_id)
    conversation_id = uuid4()
    conversation = managed.record_inbound(message, conversation_id, uuid4())
    managed.record_inbound(message, conversation_id, uuid4())
    managed.mark_inbound_processed(message.external_message_id, message.channel_type)

    items, total = managed.list(
        organization_id,
        actor(organization_id),
        bot_id=bot_id,
        channel_type="whatsapp",
        management_status="open",
        external_customer_id=None,
        has_inbound=True,
        has_outbound=False,
        page=1,
        page_size=20,
    )
    assert total == 1
    assert items[0].masked_customer_identifier == "***9999"
    assert conversation.message_count == 1

    records, total = managed.list_messages(
        organization_id,
        conversation.id,
        actor(organization_id, "operator"),
        page=1,
        page_size=20,
    )
    assert total == 1
    assert records[0].text == "Contenido sensible"
    raw = session.execute(
        select(MessageModel.content, MessageModel.text_ciphertext)
    ).one()
    assert raw.content == ""
    assert raw.text_ciphertext != "Contenido sensible"

    managed.transition(
        organization_id, conversation.id, "closed", actor(organization_id, "operator")
    )
    managed.record_inbound(
        inbound(organization_id, bot_id, message_id="wamid.2"), conversation_id, uuid4()
    )
    assert (
        managed.get(organization_id, conversation.id, actor(organization_id)).status
        == "open"
    )
    managed.transition(
        organization_id, conversation.id, "archived", actor(organization_id)
    )
    events = session.scalars(
        select(ConversationManagementEventModel)
        .where(ConversationManagementEventModel.conversation_id == conversation.id)
        .order_by(ConversationManagementEventModel.occurred_at)
    ).all()
    assert [(event.from_status, event.to_status) for event in events] == [
        ("open", "closed"),
        ("closed", "open"),
        ("open", "archived"),
    ]
    with pytest.raises(ConversationManagementConflictError):
        managed.record_inbound(
            inbound(organization_id, bot_id, message_id="wamid.3"),
            conversation_id,
            uuid4(),
        )


def test_tenant_bot_isolation_outbound_sync_and_pagination(session: Session) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    conversation_id = uuid4()
    managed.record_inbound(inbound(organization_id, bot_id), conversation_id, uuid4())
    attempt_id = uuid4()
    managed.record_outbound(
        OutboundChannelMessage(
            channel_type="whatsapp",
            external_recipient_id="51999999999",
            text="Respuesta",
        ),
        conversation_id,
        organization_id,
        bot_id,
        attempt_id,
        NOW,
    )
    managed.sync_outbound_attempt(attempt_id, "delivered", "provider-1")
    records, _ = managed.list_messages(
        organization_id,
        conversation_id,
        actor(organization_id, "operator"),
        page=1,
        page_size=1,
    )
    assert len(records) == 1
    records, total = managed.list_messages(
        organization_id,
        conversation_id,
        actor(organization_id, "operator"),
        page=1,
        page_size=2,
    )
    assert total == 2
    delivered = next(record for record in records if record.status == "delivered")
    assert delivered.provider_message_id == "provider-1"

    other_organization_id, other_bot_id = uuid4(), uuid4()
    service(session, other_organization_id, other_bot_id)
    managed.record_inbound(
        inbound(other_organization_id, other_bot_id), uuid4(), uuid4()
    )
    items, total = managed.list(
        organization_id,
        actor(organization_id),
        bot_id=None,
        channel_type=None,
        management_status=None,
        external_customer_id=None,
        has_inbound=None,
        has_outbound=None,
        page=1,
        page_size=20,
    )
    assert total == 1
    assert items[0].organization_id == organization_id


def test_active_handoff_blocks_tenant_scoped_archive(session: Session) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    conversation_id = uuid4()
    conversation = managed.record_inbound(
        inbound(organization_id, bot_id), conversation_id, uuid4()
    )
    session.add(
        HandoffSessionModel(
            conversation_id=conversation.id,
            organization_id=organization_id,
            bot_id=bot_id,
            status="human_active",
        )
    )
    session.commit()

    with pytest.raises(ConversationManagementConflictError):
        managed.transition(
            organization_id, conversation.id, "archived", actor(organization_id)
        )
