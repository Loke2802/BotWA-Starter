import base64
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

import pytest
from app.application.channel.conversation_handler import ChannelConversationHandler
from app.application.conversation_management.managed_handler import (
    ManagedChannelConversationHandler,
)
from app.application.conversation_management.service import (
    ConversationManagementConflictError,
    ConversationManagementForbiddenError,
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
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
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
    audit_writer = SqlAlchemyAuditRepository(session)
    return ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session, audit_writer),
        BotRepository(session),
        cipher(),
        session,
        audit_writer,
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
        # One stable WhatsApp line per bot unless a test switches lines.
        channel_configuration_id=uuid5(bot_id, "line"),
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


def _on_line(
    message: InboundChannelMessage, line: UUID, external_id: str
) -> InboundChannelMessage:
    return message.model_copy(
        update={
            "external_message_id": external_id,
            "resolved_context": message.resolved_context.model_copy(
                update={"channel_configuration_id": line}
            ),
        }
    )


def test_same_customer_on_two_lines_gets_one_conversation_per_line(
    session: Session,
) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    line_a, line_b = uuid4(), uuid4()
    base = inbound(organization_id, bot_id)
    first_a = _on_line(base, line_a, "wamid.a1")
    first_b = _on_line(base, line_b, "wamid.b1")
    candidate = ChannelConversationHandler.conversation_id_for(first_a)
    assert candidate == ChannelConversationHandler.conversation_id_for(first_b)

    conversation_a = managed.record_inbound(first_a, candidate, uuid4())
    conversation_b = managed.record_inbound(first_b, candidate, uuid4())
    again_b = managed.record_inbound(
        _on_line(base, line_b, "wamid.b2"), candidate, uuid4()
    )

    # The first line keeps the historical ID; the second gets its own row.
    assert conversation_a.id == candidate
    assert conversation_b.id != candidate
    assert again_b.id == conversation_b.id
    assert conversation_a.channel_configuration_id == line_a
    assert conversation_b.channel_configuration_id == line_b
    assert conversation_a.message_count == 1
    assert conversation_b.message_count == 2


def test_conversation_without_line_is_adopted_by_first_line(session: Session) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    message = inbound(organization_id, bot_id)
    candidate = ChannelConversationHandler.conversation_id_for(message)
    session.add(
        ConversationModel(
            id=candidate,
            company_id=str(organization_id),
            customer_id=message.external_sender_id,
            organization_id=organization_id,
            bot_id=bot_id,
            channel_configuration_id=None,
            external_customer_id=message.external_sender_id,
            masked_customer_identifier="***9999",
            channel="whatsapp",
            management_status="open",
            started_at=NOW,
        )
    )
    session.commit()

    conversation = managed.record_inbound(message, candidate, uuid4())

    assert conversation.id == candidate
    line = message.resolved_context.channel_configuration_id
    assert conversation.channel_configuration_id == line
    assert session.scalars(select(ConversationModel)).all() == [conversation]


class _CoreSpy:
    def __init__(self) -> None:
        self.received: list[UUID | None] = []

    conversation_id_for = staticmethod(ChannelConversationHandler.conversation_id_for)

    def handle(
        self, message: InboundChannelMessage, *, conversation_id: UUID | None = None
    ) -> OutboundChannelMessage:
        self.received.append(conversation_id)
        return OutboundChannelMessage(
            channel_type=message.channel_type,
            external_recipient_id=message.external_sender_id,
            text="core",
        )


def test_managed_flow_uses_persisted_id_of_second_line(session: Session) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    base = inbound(organization_id, bot_id)
    first = _on_line(base, uuid4(), "wamid.first-line")
    second = _on_line(base, uuid4(), "wamid.second-line")
    candidate = ChannelConversationHandler.conversation_id_for(first)
    managed.record_inbound(first, candidate, uuid4())
    core = _CoreSpy()
    handler = ManagedChannelConversationHandler(core, managed)  # type: ignore[arg-type]

    outbound = handler.handle(
        second.model_copy(update={"metadata": {"receipt_id": str(uuid4())}})
    )

    second_id = session.scalars(
        select(ConversationModel.id).where(
            ConversationModel.channel_configuration_id
            == second.resolved_context.channel_configuration_id
        )
    ).one()
    assert second_id != candidate
    assert core.received == [second_id]
    assert outbound.metadata["conversation_id"] == str(second_id)


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_exact_phone_filter_requires_sensitive_contact_access(
    session: Session, role: Role
) -> None:
    organization_id, bot_id = uuid4(), uuid4()
    managed = service(session, organization_id, bot_id)
    message = inbound(organization_id, bot_id)
    managed.record_inbound(message, uuid4(), uuid4())

    def by_phone(actor_role: Role) -> int:
        _, total = managed.list(
            organization_id,
            actor(organization_id, actor_role),
            bot_id=None,
            channel_type=None,
            management_status=None,
            external_customer_id=message.external_sender_id,
            has_inbound=None,
            has_outbound=None,
            page=1,
            page_size=20,
        )
        return total

    # Masked rows must not become a phone-number oracle for restricted roles.
    with pytest.raises(ConversationManagementForbiddenError):
        by_phone(role)
    assert by_phone("organization_owner") == 1
