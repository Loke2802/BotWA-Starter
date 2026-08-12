from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.application.conversation_management.managed_handler import (
    ManagedChannelConversationHandler,
)
from app.application.human_handoff.service import (
    HandoffConflictError,
    HumanHandoffService,
)
from app.domain.channel.contracts import (
    InboundChannelMessage,
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.analytics import HandoffCycleModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.plan_support import allow_all_plan_enforcement


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


def setup(
    session: Session, *, active: bool = True
) -> tuple[HumanHandoffService, User, UUID, UUID]:
    organization_id, bot_id, agent_id, conversation_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Org",
                slug=str(organization_id)[:12],
                status="active",
            ),
            BotModel(
                id=bot_id,
                organization_id=organization_id,
                name="Bot",
                slug="bot",
                status="active",
            ),
            UserModel(
                id=agent_id,
                organization_id=organization_id,
                email=f"{agent_id}@example.com",
                password_hash="x",
                role="organization_owner",
                status="active" if active else "inactive",
            ),
            ConversationModel(
                id=conversation_id,
                company_id=str(organization_id),
                customer_id="51999999999",
                organization_id=organization_id,
                bot_id=bot_id,
                channel_configuration_id=uuid4(),
                external_customer_id="51999999999",
                channel="whatsapp",
                management_status="open",
                status="new",
            ),
        )
    )
    session.commit()
    actor = User(
        id=agent_id,
        organization_id=organization_id,
        email=f"{agent_id}@example.com",
        role="organization_owner",
    )
    return (
        HumanHandoffService(
            HumanHandoffRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            allow_all_plan_enforcement(),
        ),
        actor,
        organization_id,
        conversation_id,
    )


def test_request_creates_waiting_human(session: Session) -> None:
    service, actor, organization_id, conversation_id = setup(session)
    result = service.request(organization_id, conversation_id, actor, "support")
    assert result.status == "waiting_human"
    assert session.scalar(select(HandoffCycleModel)) is not None


def test_each_handoff_lifecycle_uses_a_distinct_historical_cycle(
    session: Session,
) -> None:
    service, actor, organization_id, conversation_id = setup(session)
    service.request(organization_id, conversation_id, actor, "support")
    service.claim(organization_id, conversation_id, actor)
    service.resolve(organization_id, conversation_id, actor, return_to_bot=True)
    service.request(organization_id, conversation_id, actor, "follow_up")
    cycles = session.scalars(
        select(HandoffCycleModel).order_by(HandoffCycleModel.requested_at)
    ).all()
    assert len(cycles) == 2
    assert cycles[0].resolution_type == "returned_to_bot"
    assert cycles[0].resolved_at is not None
    assert cycles[0].activated_at is not None
    assert cycles[1].resolved_at is None
    assert cycles[0].id != cycles[1].id


def test_assigned_active_agent_can_claim(session: Session) -> None:
    service, actor, organization_id, conversation_id = setup(session)
    service.request(organization_id, conversation_id, actor, None)
    assert (
        service.claim(organization_id, conversation_id, actor).status == "human_active"
    )


def test_inactive_user_cannot_claim(session: Session) -> None:
    service, actor, organization_id, conversation_id = setup(session, active=False)
    service.request(
        organization_id,
        conversation_id,
        User(
            id=uuid4(),
            organization_id=organization_id,
            email="owner@example.com",
            role="organization_owner",
        ),
        None,
    )
    with pytest.raises(HandoffConflictError):
        service.claim(organization_id, conversation_id, actor)


def test_second_claim_returns_conflict(session: Session) -> None:
    service, actor, organization_id, conversation_id = setup(session)
    service.request(organization_id, conversation_id, actor, None)
    service.claim(organization_id, conversation_id, actor)
    other = User(
        id=uuid4(),
        organization_id=organization_id,
        email="other@example.com",
        role="operator",
    )
    with pytest.raises(HandoffConflictError):
        service.claim(organization_id, conversation_id, other)


class _Management:
    def record_inbound(self, *args: object) -> None:
        pass

    def mark_inbound_processed(self, *args: object) -> None:
        pass

    def mark_inbound_failed(self, *args: object) -> None:
        pass


class _Core:
    def __init__(self, conversation_id: UUID) -> None:
        self.id, self.calls = conversation_id, 0

    def conversation_id_for(self, _message: object) -> UUID:
        return self.id

    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
        self.calls += 1
        return OutboundChannelMessage(
            channel_type="whatsapp",
            external_recipient_id=message.external_sender_id,
            text="core",
        )


def _message(
    organization_id: UUID, bot_id: UUID, receipt_id: UUID
) -> InboundChannelMessage:
    return InboundChannelMessage(
        channel_type="whatsapp",
        external_message_id=str(uuid4()),
        external_sender_id="51999999999",
        external_recipient_id="1",
        text="hi",
        timestamp=datetime.now(UTC),
        resolved_context=ResolvedChannelContext(
            channel_type="whatsapp",
            organization_id=organization_id,
            bot_id=bot_id,
            channel_configuration_id=uuid4(),
            external_channel_id="1",
        ),
        metadata={"receipt_id": str(receipt_id)},
    )


@pytest.mark.parametrize("claim", [False, True])
def test_active_handoff_blocks_automatic_core_execution(
    session: Session, claim: bool
) -> None:
    service, actor, organization_id, conversation_id = setup(session)
    service.request(organization_id, conversation_id, actor, None)
    if claim:
        service.claim(organization_id, conversation_id, actor)
    core = _Core(conversation_id)
    handler = ManagedChannelConversationHandler(core, _Management(), service)  # type: ignore[arg-type]
    conversation = session.get(ConversationModel, conversation_id)
    assert conversation is not None
    assert conversation.bot_id is not None
    assert (
        handler.handle(
            _message(
                organization_id,
                conversation.bot_id,
                uuid4(),
            )
        ).metadata["handoff_blocked"]
        is True
    )
    assert core.calls == 0


def test_return_to_bot_allows_core_execution_again(session: Session) -> None:
    service, actor, organization_id, conversation_id = setup(session)
    service.request(organization_id, conversation_id, actor, None)
    service.claim(organization_id, conversation_id, actor)
    service.resolve(organization_id, conversation_id, actor, return_to_bot=True)
    core = _Core(conversation_id)
    handler = ManagedChannelConversationHandler(core, _Management(), service)  # type: ignore[arg-type]
    conversation = session.get(ConversationModel, conversation_id)
    assert conversation is not None
    assert conversation.bot_id is not None
    handler.handle(
        _message(
            organization_id,
            conversation.bot_id,
            uuid4(),
        )
    )
    assert core.calls == 1
