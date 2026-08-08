from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.application.automation_management.service import ManagedAutomationService
from app.application.business_calendar.service import BusinessCalendarService
from app.domain.automation_management.contracts import AutomationDefinitionInput
from app.domain.business_calendar.contracts import (
    BusinessCalendarCreate,
    LocalTimeInterval,
    WeeklyDayInput,
    WeeklyScheduleReplace,
)
from app.domain.business_calendar.errors import BusinessCalendarConflict
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    database = sessionmaker(bind=engine)()
    try:
        yield database
    finally:
        database.close()
        engine.dispose()


def _legacy_hours() -> dict[str, object]:
    closed = {"enabled": False, "open_time": "09:00", "close_time": "17:00"}
    return {
        "monday": {"enabled": True, "open_time": "09:00", "close_time": "17:00"},
        "tuesday": closed,
        "wednesday": closed,
        "thursday": closed,
        "friday": closed,
        "saturday": closed,
        "sunday": closed,
    }


def _setup(session: Session) -> tuple[ManagedAutomationService, User, UUID, UUID]:
    organization_id, bot_id, user_id = uuid4(), uuid4(), uuid4()
    actor = User(
        id=user_id,
        organization_id=organization_id,
        email="prd015-compat@example.invalid",
        role="organization_owner",
    )
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Compatibility tenant",
                slug=f"compat-{str(organization_id)[:8]}",
                status="active",
            ),
            BotModel(
                id=bot_id,
                organization_id=organization_id,
                name="Compatibility bot",
                slug="compatibility-bot",
                status="active",
            ),
            UserModel(
                id=user_id,
                organization_id=organization_id,
                email=actor.email,
                password_hash="x",
                role=actor.role,
                status="active",
            ),
            BusinessConfigurationModel(
                bot_id=bot_id,
                business_name="Legacy schedule",
                description="PRD-005 fallback",
                timezone="UTC",
                business_hours=_legacy_hours(),
                services=[],
                payment_methods=[],
                policies=[],
                service_instructions="",
                handoff_enabled=True,
                handoff_outside_business_hours=True,
                status="configured",
            ),
        )
    )
    session.commit()
    return (
        ManagedAutomationService(ManagedAutomationRepository(session), session),
        actor,
        organization_id,
        bot_id,
    )


def _active_calendar(
    session: Session,
    actor: User,
    organization_id: UUID,
    bot_id: UUID | None,
    *,
    activate: bool = True,
) -> UUID:
    calendars = BusinessCalendarService(
        BusinessCalendarRepository(session),
        session,
    )
    created = calendars.create_calendar(
        organization_id,
        BusinessCalendarCreate(
            name=f"PRD-015 {'organization default' if bot_id is None else bot_id}",
            bot_id=bot_id,
            timezone="UTC",
        ),
        actor,
    )
    calendars.replace_weekly_schedule(
        organization_id,
        created.id,
        WeeklyScheduleReplace(
            expected_version=created.version,
            days=[
                WeeklyDayInput(
                    weekday=1,
                    intervals=[LocalTimeInterval(start="12:00", end="14:00")],
                )
            ],
        ),
        actor,
    )
    if activate:
        calendars.transition_calendar(organization_id, created.id, "activate", actor)
    return created.id


def test_bot_calendar_precedes_active_organization_default(session: Session) -> None:
    _automations, actor, organization_id, bot_id = _setup(session)
    _active_calendar(session, actor, organization_id, None)
    _active_calendar(session, actor, organization_id, bot_id)

    calendars = BusinessCalendarService(BusinessCalendarRepository(session), session)
    applicable = calendars.repository.active_applicable_calendar(
        organization_id,
        bot_id,
    )

    assert applicable is not None
    assert applicable.bot_id == bot_id


def test_active_prd015_is_source_of_truth_and_prd005_is_explicit_fallback(
    session: Session,
) -> None:
    automations, actor, organization_id, bot_id = _setup(session)
    monday_10 = datetime(2026, 8, 10, 10, tzinfo=UTC)
    monday_13 = datetime(2026, 8, 10, 13, tzinfo=UTC)

    assert (
        automations.business_hours_state(organization_id, bot_id, monday_10) == "inside"
    )
    calendar_id = _active_calendar(
        session,
        actor,
        organization_id,
        bot_id,
        activate=False,
    )
    assert (
        automations.business_hours_state(organization_id, bot_id, monday_10) == "inside"
    )
    BusinessCalendarService(
        BusinessCalendarRepository(session),
        session,
    ).transition_calendar(organization_id, calendar_id, "activate", actor)
    assert (
        automations.business_hours_state(organization_id, bot_id, monday_10)
        == "outside"
    )
    assert (
        automations.business_hours_state(organization_id, bot_id, monday_13) == "inside"
    )

    unknown_bot = uuid4()
    session.add(
        BotModel(
            id=unknown_bot,
            organization_id=organization_id,
            name="No schedule",
            slug="no-schedule",
            status="active",
        )
    )
    session.commit()
    assert (
        automations.business_hours_state(organization_id, unknown_bot, monday_10)
        == "unknown"
    )


def test_prd012_inbound_snapshot_consumes_prd015_state_without_lost_scope(
    session: Session,
) -> None:
    automations, actor, organization_id, bot_id = _setup(session)
    _active_calendar(session, actor, organization_id, bot_id)
    conversation_id = uuid4()
    session.add(
        ConversationModel(
            id=conversation_id,
            company_id=str(organization_id),
            customer_id="synthetic",
            organization_id=organization_id,
            bot_id=bot_id,
            channel="whatsapp",
            management_status="open",
            status="new",
        )
    )
    session.commit()
    definition = automations.create(
        organization_id,
        AutomationDefinitionInput(
            name="Outside-hours handoff",
            bot_id=str(bot_id),
            trigger_type="conversation.inbound_received",
            conditions_data={"business_hours_state": "outside"},
            action_type="request_handoff",
            action_data={"reason_code": "outside_business_hours"},
        ),
        actor,
    )
    automations.transition(organization_id, definition.id, "activate", actor)
    occurred_at = datetime(2026, 8, 10, 10, tzinfo=UTC)
    state = automations.business_hours_state(
        organization_id,
        bot_id,
        occurred_at,
    )
    automations.record_inbound(
        organization_id=organization_id,
        bot_id=bot_id,
        conversation_id=conversation_id,
        contact_id=None,
        channel_type="whatsapp",
        received_at=occurred_at,
        business_hours_state=state,
        source_receipt_id=uuid4(),
    )

    receipt = session.scalars(select(ManagedAutomationEventReceiptModel)).one()
    execution = session.scalars(select(ManagedAutomationExecutionModel)).one()
    assert receipt.event_type == "conversation.inbound_received"
    assert receipt.event_data["business_hours_state"] == "outside"
    assert execution.event_snapshot["business_hours_state"] == "outside"


def test_only_one_active_calendar_is_allowed_per_tenant_scope(
    session: Session,
) -> None:
    _automations, actor, organization_id, bot_id = _setup(session)
    _active_calendar(session, actor, organization_id, bot_id)
    calendars = BusinessCalendarService(BusinessCalendarRepository(session), session)
    duplicate = calendars.create_calendar(
        organization_id,
        BusinessCalendarCreate(
            name="Conflicting calendar",
            bot_id=bot_id,
            timezone="UTC",
        ),
        actor,
    )

    with pytest.raises(BusinessCalendarConflict):
        calendars.transition_calendar(
            organization_id,
            duplicate.id,
            "activate",
            actor,
        )
