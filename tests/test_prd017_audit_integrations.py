import base64
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.application.automation_management.service import ManagedAutomationService
from app.application.bots.service import BotService
from app.application.business_calendar.service import BusinessCalendarService
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.domain.audit.contracts import AuditEventDraft
from app.domain.automation_management.contracts import AutomationDefinitionInput
from app.domain.bot.contracts import BotCreate, BotUpdate
from app.domain.business_calendar.contracts import (
    BusinessCalendarCreate,
    BusinessCalendarUpdate,
    LocalTimeInterval,
    WeeklyDayInput,
    WeeklyScheduleReplace,
)
from app.domain.channel.contracts import InboundChannelMessage, ResolvedChannelContext
from app.domain.integration_management.contracts import (
    IntegrationConnectionUpdate,
    IntegrationCredentialInput,
)
from app.domain.organization.contracts import OrganizationCreate, OrganizationUpdate
from app.domain.user.contracts import User, UserCreate, UserUpdate
from app.infrastructure.database import Base
from app.infrastructure.models.analytics import ConversationManagementEventModel
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_calendar import BusinessCalendarAuditEventModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffEventModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
    SqlAlchemyConversationMessageManagementRepository,
)
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.security.passwords import PasswordService
from app.security.secret_cipher import EnvironmentSecretCipher
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.test_prd013_integration_management import (
    _payload as integration_payload,
)
from tests.test_prd013_integration_management import (
    _setup as integration_setup,
)

NOW = datetime(2026, 8, 8, 19, tzinfo=UTC)


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
        engine.dispose()


def _actions(session: Session, organization_id: UUID) -> list[str]:
    return list(
        session.scalars(
            select(AuditEventModel.action)
            .where(AuditEventModel.organization_id == organization_id)
            .order_by(AuditEventModel.occurred_at, AuditEventModel.id)
        ).all()
    )


def _seed_actor_scope(session: Session) -> tuple[UUID, UUID, User]:
    organization_id, bot_id, actor_id = uuid4(), uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Audit scope",
                slug=f"audit-scope-{organization_id}",
                status="active",
            ),
            BotModel(
                id=bot_id,
                organization_id=organization_id,
                name="Luri",
                slug="luri",
                status="active",
            ),
            UserModel(
                id=actor_id,
                organization_id=organization_id,
                email=f"{actor_id}@audit.invalid",
                password_hash=PasswordService().hash("owner-password-123"),
                role="organization_owner",
                status="active",
            ),
        )
    )
    session.commit()
    actor = User(
        id=actor_id,
        organization_id=organization_id,
        email=f"{actor_id}@audit.invalid",
        role="organization_owner",
    )
    return organization_id, bot_id, actor


def test_organization_user_access_and_bot_actions_are_atomic(session: Session) -> None:
    writer = SqlAlchemyAuditRepository(session)
    organizations = OrganizationService(
        OrganizationRepository(session), session, writer
    )
    organization = organizations.create(
        OrganizationCreate(name="Kalivur", slug=f"kalivur-{uuid4()}")
    )
    users = UserService(
        UserRepository(session),
        OrganizationRepository(session),
        PasswordService(),
        session,
        writer,
    )
    owner = users.create(
        UserCreate(
            organization_id=organization.id,
            email=f"owner-{uuid4()}@example.com",
            password="owner-password-123",
        )
    )
    member = users.create(
        UserCreate(
            organization_id=organization.id,
            email=f"member-{uuid4()}@example.com",
            password="member-password-123",
        ),
        actor=owner,
    )
    users.update(member.id, UserUpdate(first_name="Agent"), actor=owner)
    users.assign_role(member.id, "operator", actor=owner)
    users.change_password(
        member.id,
        "member-password-123",
        "member-password-456",
        actor=member,
    )
    users.deactivate(member.id, actor=owner)
    bots = BotService(
        BotRepository(session), OrganizationRepository(session), session, writer
    )
    bot = bots.create(
        BotCreate(
            organization_id=organization.id,
            name="Luri",
            slug=f"luri-{uuid4()}",
        ),
        actor=owner,
    )
    bots.update(bot.id, BotUpdate(name="Luri Support"), actor=owner)
    bots.activate(bot.id, actor=owner)
    bots.deactivate(bot.id, actor=owner)
    organizations.update(
        organization.id, OrganizationUpdate(name="Kalivur SAC"), actor=owner
    )
    organizations.deactivate(organization.id, actor=owner)
    assert set(_actions(session, organization.id)) >= {
        "organization.created",
        "organization.updated",
        "organization.deactivated",
        "user.created",
        "user.updated",
        "user.role_changed",
        "user.password_changed",
        "user.deactivated",
        "bot.created",
        "bot.updated",
        "bot.activated",
        "bot.deactivated",
    }
    metadata_rows = session.scalars(select(AuditEventModel.metadata_data)).all()
    serialized = str(metadata_rows).lower()
    assert "@example.com" not in serialized
    assert "password-" not in serialized


def test_audit_fk_failure_rolls_back_business_mutation(session: Session) -> None:
    organization_id = uuid4()
    session.add(
        OrganizationModel(
            id=organization_id,
            name="Tenant",
            slug=f"tenant-{organization_id}",
            status="active",
        )
    )
    session.commit()
    actor = User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"missing-{uuid4()}@audit.invalid",
        role="organization_owner",
    )

    class InvalidAuditWriter:
        def append(self, draft: AuditEventDraft) -> None:
            session.add(
                AuditEventModel(
                    organization_id=draft.organization_id,
                    actor_type=draft.actor_type,
                    actor_user_id=draft.actor_user_id,
                    actor_role=draft.actor_role,
                    action=draft.action,
                    resource_type=draft.resource_type,
                    resource_id=draft.resource_id,
                    result="failed",
                    metadata_data={},
                    occurred_at=draft.occurred_at,
                    created_at=draft.occurred_at,
                )
            )

    service = BotService(
        BotRepository(session),
        OrganizationRepository(session),
        session,
        InvalidAuditWriter(),
    )
    with pytest.raises(ValueError, match="persistence failed"):
        service.create(
            BotCreate(name="Rollback", slug=f"rollback-{uuid4()}"), actor=actor
        )
    assert (
        session.scalar(
            select(func.count(BotModel.id)).where(
                BotModel.organization_id == organization_id
            )
        )
        == 0
    )
    assert (
        session.scalar(
            select(func.count(AuditEventModel.id)).where(
                AuditEventModel.organization_id == organization_id
            )
        )
        == 0
    )


def test_conversation_and_handoff_keep_domain_history_plus_generic_audit(
    session: Session,
) -> None:
    organization_id, bot_id, actor = _seed_actor_scope(session)
    writer = SqlAlchemyAuditRepository(session)
    cipher = EnvironmentSecretCipher(
        base64.urlsafe_b64encode(b"a" * 32).decode("ascii")
    )
    conversation_id = uuid4()
    management = ConversationManagementService(
        SqlAlchemyConversationManagementRepository(session),
        SqlAlchemyConversationMessageManagementRepository(session, writer),
        BotRepository(session),
        cipher,
        session,
        writer,
    )
    inbound = InboundChannelMessage(
        channel_type="whatsapp",
        external_message_id="wamid.audit.1",
        external_sender_id="51999999999",
        external_recipient_id="123",
        text="sensitive text",
        timestamp=NOW,
        resolved_context=ResolvedChannelContext(
            channel_type="whatsapp",
            organization_id=organization_id,
            bot_id=bot_id,
            channel_configuration_id=uuid4(),
            external_channel_id="123",
        ),
    )
    conversation = management.record_inbound(inbound, conversation_id, uuid4())
    management.transition(organization_id, conversation.id, "closed", actor)
    management.transition(organization_id, conversation.id, "open", actor)
    management.transition(organization_id, conversation.id, "closed", actor)
    management.record_inbound(
        inbound.model_copy(update={"external_message_id": "wamid.audit.2"}),
        conversation.id,
        uuid4(),
    )
    management.transition(organization_id, conversation.id, "archived", actor)

    handoff_conversation = ConversationModel(
        id=uuid4(),
        company_id=str(organization_id),
        customer_id="masked",
        organization_id=organization_id,
        bot_id=bot_id,
        channel="whatsapp",
        management_status="open",
        status="new",
    )
    session.add(handoff_conversation)
    session.commit()
    handoff = HumanHandoffService(HumanHandoffRepository(session), session, writer)
    handoff.request(organization_id, handoff_conversation.id, actor, "support")
    handoff.claim(organization_id, handoff_conversation.id, actor)
    handoff.release(organization_id, handoff_conversation.id, actor)
    handoff.claim(organization_id, handoff_conversation.id, actor)
    handoff.transfer(organization_id, handoff_conversation.id, actor, actor.id)
    handoff.resolve(organization_id, handoff_conversation.id, actor, return_to_bot=True)
    handoff.request_automation(
        organization_id, handoff_conversation.id, "automation_rule"
    )
    handoff.claim(organization_id, handoff_conversation.id, actor)
    handoff.resolve(
        organization_id, handoff_conversation.id, actor, return_to_bot=False
    )
    actions = _actions(session, organization_id)
    assert set(actions) >= {
        "conversation.closed",
        "conversation.reopened",
        "conversation.archived",
        "handoff.requested",
        "handoff.claimed",
        "handoff.released",
        "handoff.transferred",
        "handoff.returned_to_bot",
        "handoff.resolved",
    }
    automation_request = session.scalars(
        select(AuditEventModel).where(
            AuditEventModel.action == "handoff.requested",
            AuditEventModel.actor_type == "automation",
        )
    ).one()
    assert automation_request.actor_user_id is None
    assert session.scalar(select(func.count(ConversationManagementEventModel.id))) == 5
    assert session.scalar(select(func.count(HandoffEventModel.id))) == 9
    assert "sensitive text" not in str(
        session.scalars(select(AuditEventModel.metadata_data)).all()
    )


def test_automation_integration_and_calendar_emit_only_admin_audit(
    session: Session,
) -> None:
    organization_id, bot_id, actor = _seed_actor_scope(session)
    writer = SqlAlchemyAuditRepository(session)
    automation = ManagedAutomationService(
        ManagedAutomationRepository(session), session, audit_writer=writer
    )
    definition = automation.create(
        organization_id,
        AutomationDefinitionInput(
            name="Handoff",
            bot_id=str(bot_id),
            trigger_type="conversation.inbound_received",
            action_type="request_handoff",
        ),
        actor,
    )
    automation.update(organization_id, definition.id, {"name": "Handoff v2"}, actor)
    receipt = ManagedAutomationEventReceiptModel(
        organization_id=organization_id,
        bot_id=bot_id,
        source_type="conversation",
        source_event_id=uuid4(),
        event_type="conversation.inbound_received",
        event_data={},
        correlation_id=uuid4(),
        occurred_at=NOW,
    )
    session.add(receipt)
    session.flush()
    execution = ManagedAutomationExecutionModel(
        organization_id=organization_id,
        automation_definition_id=definition.id,
        definition_version=definition.version,
        event_receipt_id=receipt.id,
        definition_snapshot={},
        event_snapshot={},
        status="failed",
        attempt_count=2,
        available_at=NOW,
        correlation_id=uuid4(),
    )
    session.add(execution)
    session.commit()
    automation.retry_execution(organization_id, execution.id, actor)
    automation.transition(organization_id, definition.id, "activate", actor)
    automation.transition(organization_id, definition.id, "deactivate", actor)
    automation.transition(organization_id, definition.id, "archive", actor)

    integration, _adapter, integration_actor, integration_org, integration_bot = (
        integration_setup(session)
    )
    integration.audit_writer = writer
    connection = integration.create(
        integration_org, integration_payload(integration_bot), integration_actor
    )
    integration.update(
        integration_org,
        connection.id,
        IntegrationConnectionUpdate(name="Calendar v2"),
        integration_actor,
    )
    integration.update_credentials(
        integration_org,
        connection.id,
        IntegrationCredentialInput(refresh_token="super-secret-refresh"),
        integration_actor,
    )
    integration.activate(integration_org, connection.id, integration_actor)
    integration.deactivate(integration_org, connection.id, integration_actor)
    integration.archive(integration_org, connection.id, integration_actor)

    calendar = BusinessCalendarService(
        BusinessCalendarRepository(session), session, audit_writer=writer
    )
    calendar_response = calendar.create_calendar(
        organization_id,
        BusinessCalendarCreate(name="Support", timezone="UTC", bot_id=bot_id),
        actor,
        idempotency_key="audit-calendar-create-001",
    )
    replay = calendar.create_calendar(
        organization_id,
        BusinessCalendarCreate(name="Support", timezone="UTC", bot_id=bot_id),
        actor,
        idempotency_key="audit-calendar-create-001",
    )
    assert replay.id == calendar_response.id
    updated = calendar.update_calendar(
        organization_id,
        calendar_response.id,
        BusinessCalendarUpdate(expected_version=1, name="Support v2"),
        actor,
    )
    scheduled = calendar.replace_weekly_schedule(
        organization_id,
        calendar_response.id,
        WeeklyScheduleReplace(
            expected_version=updated.version,
            days=[
                WeeklyDayInput(
                    weekday=1,
                    intervals=[LocalTimeInterval(start="09:00", end="17:00")],
                )
            ],
        ),
        actor,
        idempotency_key="audit-calendar-schedule-001",
    )
    calendar.transition_calendar(
        organization_id, calendar_response.id, "activate", actor
    )
    calendar.transition_calendar(
        organization_id, calendar_response.id, "deactivate", actor
    )
    calendar.transition_calendar(
        organization_id, calendar_response.id, "archive", actor
    )
    assert scheduled.calendar_version >= 3
    assert set(_actions(session, organization_id)) >= {
        "automation.created",
        "automation.updated",
        "automation.retry_requested",
        "automation.activated",
        "automation.deactivated",
        "automation.archived",
        "business_calendar.created",
        "business_calendar.updated",
        "business_calendar.activated",
        "business_calendar.deactivated",
        "business_calendar.archived",
    }
    assert set(_actions(session, integration_org)) >= {
        "integration.created",
        "integration.updated",
        "integration.credentials_rotated",
        "integration.activated",
        "integration.deactivated",
        "integration.archived",
    }
    assert _actions(session, organization_id).count("business_calendar.created") == 1
    assert session.scalar(select(func.count(BusinessCalendarAuditEventModel.id))) == 6
    assert len(_actions(session, integration_org)) == 6
    serialized = str(
        session.scalars(
            select(AuditEventModel.metadata_data).where(
                AuditEventModel.organization_id == integration_org
            )
        ).all()
    )
    assert "super-secret-refresh" not in serialized
