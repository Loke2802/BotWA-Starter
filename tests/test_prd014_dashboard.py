from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import cast, get_args
from uuid import UUID, uuid4

import pytest
from app.api.dashboard_dependencies import get_dashboard_query_service
from app.api.dashboard_routes import router
from app.api.dependencies import require_authenticated_user
from app.application.business_calendar.compatibility import (
    BusinessHoursStateCompatibilityService,
)
from app.application.business_calendar.service import BusinessCalendarService
from app.application.dashboard.business import DashboardBusinessStatusReader
from app.application.dashboard.service import DashboardQueryService
from app.domain.access.contracts import Role
from app.domain.bot.contracts import BotStatus
from app.domain.business_calendar.errors import BusinessCalendarPersistenceError
from app.domain.conversation_management.contracts import ConversationStatus
from app.domain.dashboard.contracts import DashboardBusinessSummary
from app.domain.dashboard.errors import (
    DashboardInvalidFilter,
    DashboardNotFound,
    DashboardRangeTooLarge,
)
from app.domain.organization.contracts import DEFAULT_ORGANIZATION_TIMEZONE
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_calendar import (
    BusinessCalendarAuditEventModel,
    BusinessCalendarIdempotencyReceiptModel,
    BusinessCalendarModel,
    BusinessCalendarWeeklyIntervalModel,
)
from app.infrastructure.models.business_configuration import (
    BusinessConfigurationModel,
)
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.integration_management import IntegrationConnectionModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.repositories.dashboard_repository import (
    SqlAlchemyDashboardRepository,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


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


def _actor(organization_id: UUID, role: Role = "organization_owner") -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"dashboard-{uuid4()}@example.invalid",
        role=role,
    )


def _base(session: Session) -> tuple[UUID, UUID, UUID, UUID, User]:
    organization_id, foreign_id = uuid4(), uuid4()
    bot_a1, bot_a2, bot_b = uuid4(), uuid4(), uuid4()
    actor = _actor(organization_id)
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Tenant A",
                slug=f"tenant-a-{str(organization_id)[:8]}",
                status="active",
                settings={"locale": "es", "timezone": "UTC"},
            ),
            OrganizationModel(
                id=foreign_id,
                name="Tenant B",
                slug=f"tenant-b-{str(foreign_id)[:8]}",
                status="active",
                settings={"locale": "es", "timezone": "UTC"},
            ),
            BotModel(
                id=bot_a1,
                organization_id=organization_id,
                name="A1",
                slug="a1",
                status="active",
                timezone="UTC",
            ),
            BotModel(
                id=bot_a2,
                organization_id=organization_id,
                name="A2",
                slug="a2",
                status="inactive",
                timezone="UTC",
            ),
            BotModel(
                id=bot_b,
                organization_id=foreign_id,
                name="B",
                slug="b",
                status="active",
                timezone="UTC",
            ),
        )
    )
    session.commit()
    return organization_id, foreign_id, bot_a1, bot_a2, actor


def _service(session: Session) -> DashboardQueryService:
    calendars = BusinessCalendarService(BusinessCalendarRepository(session), session)
    return DashboardQueryService(
        SqlAlchemyDashboardRepository(session),
        DashboardBusinessStatusReader(
            calendars,
            BusinessHoursStateCompatibilityService(calendars, session),
        ),
    )


def _conversation(
    organization_id: UUID,
    bot_id: UUID,
    management_status: str,
    started_at: datetime,
) -> ConversationModel:
    return ConversationModel(
        id=uuid4(),
        company_id=str(organization_id),
        customer_id=str(uuid4()),
        organization_id=organization_id,
        bot_id=bot_id,
        channel="whatsapp",
        status="active",
        management_status=management_status,
        started_at=started_at,
        created_at=started_at,
        updated_at=started_at,
    )


def _automation(
    organization_id: UUID,
    bot_id: UUID,
    actor_id: UUID,
    execution_status: str,
    created_at: datetime,
) -> tuple[object, ...]:
    definition_id, receipt_id = uuid4(), uuid4()
    definition = ManagedAutomationDefinitionModel(
        id=definition_id,
        organization_id=organization_id,
        bot_id=bot_id,
        name=f"Automation {definition_id}",
        trigger_type="conversation.inbound_received",
        conditions_data={},
        action_type="request_handoff",
        action_data={"reason_code": "automation_rule"},
        status="active",
        version=1,
        created_by_user_id=actor_id,
        updated_by_user_id=actor_id,
        created_at=created_at,
        updated_at=created_at,
    )
    receipt = ManagedAutomationEventReceiptModel(
        id=receipt_id,
        organization_id=organization_id,
        bot_id=bot_id,
        source_type="conversation",
        source_event_id=uuid4(),
        event_type="conversation.inbound_received",
        event_data={},
        correlation_id=uuid4(),
        occurred_at=created_at,
        created_at=created_at,
    )
    execution = ManagedAutomationExecutionModel(
        id=uuid4(),
        organization_id=organization_id,
        automation_definition_id=definition_id,
        definition_version=1,
        event_receipt_id=receipt_id,
        definition_snapshot={},
        event_snapshot={},
        status=execution_status,
        attempt_count=1,
        available_at=created_at,
        correlation_id=uuid4(),
        created_at=created_at,
        updated_at=created_at,
    )
    return definition, receipt, execution


def _populate(
    session: Session,
    organization_id: UUID,
    foreign_id: UUID,
    bot_a1: UUID,
    bot_a2: UUID,
    actor: User,
) -> UUID:
    bot_b = cast(
        UUID,
        session.scalar(
            select(BotModel.id).where(BotModel.organization_id == foreign_id)
        ),
    )
    open_conversation = _conversation(
        organization_id, bot_a1, "open", NOW - timedelta(hours=1)
    )
    closed_conversation = _conversation(
        organization_id, bot_a2, "closed", NOW - timedelta(days=2)
    )
    foreign_conversation = _conversation(
        foreign_id, bot_b, "open", NOW - timedelta(hours=1)
    )
    calendar_id = uuid4()
    session.add_all(
        (
            open_conversation,
            closed_conversation,
            foreign_conversation,
            ContactModel(
                id=uuid4(),
                organization_id=organization_id,
                channel_type="whatsapp",
                external_identifier_hash="a" * 64,
                external_identifier_ciphertext="encrypted-a",
                status="active",
                created_at=NOW - timedelta(hours=2),
                updated_at=NOW,
            ),
            ContactModel(
                id=uuid4(),
                organization_id=organization_id,
                channel_type="whatsapp",
                external_identifier_hash="b" * 64,
                external_identifier_ciphertext="encrypted-b",
                status="archived",
                created_at=NOW - timedelta(days=40),
                updated_at=NOW,
            ),
            ContactModel(
                id=uuid4(),
                organization_id=foreign_id,
                channel_type="whatsapp",
                external_identifier_hash="c" * 64,
                external_identifier_ciphertext="encrypted-c",
                status="active",
                created_at=NOW,
                updated_at=NOW,
            ),
            HandoffSessionModel(
                id=uuid4(),
                conversation_id=open_conversation.id,
                organization_id=organization_id,
                bot_id=bot_a1,
                status="human_active",
                requested_at=NOW - timedelta(hours=2),
                last_activity_at=NOW - timedelta(minutes=5),
                created_at=NOW - timedelta(hours=2),
                updated_at=NOW,
            ),
            HandoffSessionModel(
                id=uuid4(),
                conversation_id=closed_conversation.id,
                organization_id=organization_id,
                bot_id=bot_a2,
                status="resolved",
                resolved_at=NOW - timedelta(hours=1),
                last_activity_at=NOW - timedelta(hours=1),
                created_at=NOW - timedelta(days=2),
                updated_at=NOW,
            ),
            IntegrationConnectionModel(
                id=uuid4(),
                organization_id=organization_id,
                bot_id=bot_a1,
                name="A1 calendar",
                integration_type="calendar",
                provider="google_calendar",
                status="active",
                version=1,
                capabilities=["calendar.metadata.read"],
                configuration={"read_only": True},
                health_status="healthy",
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
                created_at=NOW,
                updated_at=NOW,
            ),
            IntegrationConnectionModel(
                id=uuid4(),
                organization_id=organization_id,
                bot_id=bot_a2,
                name="A2 calendar",
                integration_type="calendar",
                provider="google_calendar",
                status="inactive",
                version=1,
                capabilities=["calendar.metadata.read"],
                configuration={"read_only": True},
                health_status="degraded",
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
                created_at=NOW,
                updated_at=NOW,
            ),
            IntegrationConnectionModel(
                id=uuid4(),
                organization_id=foreign_id,
                bot_id=bot_b,
                name="B calendar",
                integration_type="calendar",
                provider="google_calendar",
                status="active",
                version=1,
                capabilities=["calendar.metadata.read"],
                configuration={"read_only": True},
                health_status="auth_error",
                created_by_user_id=uuid4(),
                updated_by_user_id=uuid4(),
                created_at=NOW,
                updated_at=NOW,
            ),
            BusinessCalendarModel(
                id=calendar_id,
                organization_id=organization_id,
                name="Organization hours",
                timezone="UTC",
                status="active",
                version=1,
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
                created_at=NOW,
                updated_at=NOW,
            ),
            BusinessCalendarWeeklyIntervalModel(
                id=uuid4(),
                organization_id=organization_id,
                calendar_id=calendar_id,
                weekday=1,
                start_minute=9 * 60,
                end_minute=17 * 60,
                created_at=NOW,
            ),
            *_automation(
                organization_id, bot_a1, actor.id, "succeeded", NOW - timedelta(hours=1)
            ),
            *_automation(
                organization_id, bot_a2, actor.id, "failed", NOW - timedelta(days=2)
            ),
            *_automation(
                foreign_id, bot_b, uuid4(), "pending", NOW - timedelta(hours=1)
            ),
        )
    )
    session.commit()
    return bot_b


def _business_write_counts(session: Session) -> tuple[int, int]:
    return (
        session.scalar(
            select(func.count()).select_from(BusinessCalendarAuditEventModel)
        )
        or 0,
        session.scalar(
            select(func.count()).select_from(BusinessCalendarIdempotencyReceiptModel)
        )
        or 0,
    )


def test_dashboard_lifecycle_totals_follow_canonical_contracts(
    session: Session,
) -> None:
    assert set(get_args(BotStatus)) == {"active", "inactive"}
    assert set(get_args(ConversationStatus)) == {"open", "closed", "archived"}
    organization_id, _foreign_id, bot_a1, _bot_a2, actor = _base(session)
    canonical = tuple(
        _conversation(organization_id, bot_a1, status, NOW - timedelta(hours=index))
        for index, status in enumerate(("open", "closed", "archived"), start=1)
    )
    legacy = _conversation(organization_id, bot_a1, "open", NOW)
    legacy.management_status = None
    session.add_all((*canonical, legacy))
    session.commit()

    result = _service(session).summary(
        organization_id, actor, period="today", generated_at=NOW
    )

    assert result.bots.total == result.bots.active + result.bots.inactive
    assert result.conversations.total == (
        result.conversations.open
        + result.conversations.closed
        + result.conversations.archived
    )
    assert result.conversations.model_dump(exclude={"scope", "started_in_period"}) == {
        "total": 3,
        "open": 1,
        "closed": 1,
        "archived": 1,
    }


def test_empty_and_populated_dashboard_aggregate_without_cross_tenant_data(
    session: Session,
) -> None:
    organization_id, foreign_id, bot_a1, bot_a2, actor = _base(session)
    empty = _service(session).summary(
        organization_id, actor, period="today", generated_at=NOW
    )
    assert empty.bots.total == 2
    assert empty.conversations.total == 0
    assert empty.contacts.total == 0
    assert empty.business.status == "unknown"

    _populate(session, organization_id, foreign_id, bot_a1, bot_a2, actor)
    result = _service(session).summary(
        organization_id, actor, period="last_7_days", generated_at=NOW
    )
    assert result.bots.model_dump(exclude={"scope"}) == {
        "total": 2,
        "active": 1,
        "inactive": 1,
    }
    assert result.conversations.total == 2
    assert result.conversations.open == 1
    assert result.conversations.closed == 1
    assert result.conversations.started_in_period == 2
    assert result.handoffs.active == 1
    assert result.handoffs.pending == 0
    assert result.handoffs.created_in_period == 2
    assert result.handoffs.completed_in_period == 1
    assert result.handoffs.oldest_active_age_seconds == 7200
    assert result.automations.total == 2
    assert result.automations.succeeded == 1
    assert result.automations.failed == 1
    assert result.integrations.total == 2
    assert result.integrations.active == 1
    assert result.integrations.healthy == 1
    assert result.integrations.degraded == 0
    assert result.integrations.active == (
        result.integrations.healthy
        + result.integrations.degraded
        + result.integrations.unreachable
        + result.integrations.auth_error
        + result.integrations.unknown
    )
    assert result.contacts.total == 2
    assert result.contacts.created_in_period == 1
    assert result.contacts.scope == "organization"
    assert result.business.status == "open"
    assert result.business.source == "prd_015"
    assert not session.new
    assert not session.dirty
    assert not session.deleted
    assert _business_write_counts(session) == (0, 0)

    bot_result = _service(session).summary(
        organization_id,
        actor,
        bot_id=bot_a1,
        period="last_7_days",
        generated_at=NOW,
    )
    assert bot_result.bots.total == 1
    assert bot_result.conversations.total == 1
    assert bot_result.handoffs.active == 1
    assert bot_result.automations.succeeded == 1
    assert bot_result.automations.failed == 0
    assert bot_result.integrations.total == 1
    assert bot_result.contacts.total == 2
    assert bot_result.business.status == "open"
    assert bot_result.business.source == "prd_015"
    assert not session.new
    assert not session.dirty
    assert not session.deleted
    assert _business_write_counts(session) == (0, 0)

    with pytest.raises(DashboardNotFound):
        _service(session).summary(
            organization_id,
            actor,
            bot_id=cast(
                UUID,
                session.scalar(
                    select(BotModel.id).where(BotModel.organization_id == foreign_id)
                ),
            ),
            generated_at=NOW,
        )


def test_periods_timezone_ranges_and_read_only_guarantee(session: Session) -> None:
    organization_id, foreign_id, bot_a1, bot_a2, actor = _base(session)
    _populate(session, organization_id, foreign_id, bot_a1, bot_a2, actor)
    service = _service(session)
    today = service.summary(organization_id, actor, period="today", generated_at=NOW)
    assert today.period.from_ == datetime(2026, 8, 10, tzinfo=UTC)
    assert today.period.to == datetime(2026, 8, 11, tzinfo=UTC)
    seven = service.summary(
        organization_id, actor, period="last_7_days", generated_at=NOW
    )
    assert seven.period.from_ == datetime(2026, 8, 4, tzinfo=UTC)
    thirty = service.summary(
        organization_id, actor, period="last_30_days", generated_at=NOW
    )
    assert thirty.period.from_ == datetime(2026, 7, 12, tzinfo=UTC)
    custom = service.summary(
        organization_id,
        actor,
        from_=NOW - timedelta(days=3),
        to=NOW,
        generated_at=NOW,
    )
    assert custom.period.preset == "custom"
    assert custom.period.to == NOW
    exact_limit = service.summary(
        organization_id,
        actor,
        from_=NOW - timedelta(days=90),
        to=NOW,
        generated_at=NOW,
    )
    assert exact_limit.period.from_ == NOW - timedelta(days=90)
    with pytest.raises(DashboardRangeTooLarge):
        service.summary(
            organization_id,
            actor,
            from_=NOW - timedelta(days=90, microseconds=1),
            to=NOW,
            generated_at=NOW,
        )
    with pytest.raises(DashboardInvalidFilter):
        service.summary(
            organization_id,
            actor,
            period="today",
            from_=NOW - timedelta(days=1),
            to=NOW,
            generated_at=NOW,
        )
    assert not session.new
    assert not session.dirty
    assert not session.deleted
    assert _business_write_counts(session) == (0, 0)

    organization = session.get(OrganizationModel, organization_id)
    assert organization is not None
    organization.settings = {"locale": "es"}
    session.commit()
    fallback = service.summary(organization_id, actor, period="today", generated_at=NOW)
    assert fallback.period.timezone == DEFAULT_ORGANIZATION_TIMEZONE
    assert fallback.period.from_ == datetime(2026, 8, 10, 5, 0, tzinfo=UTC)


def test_timezone_dst_and_prd005_fallback_use_canonical_contracts(
    session: Session,
) -> None:
    organization_id, _foreign_id, bot_a1, _bot_a2, actor = _base(session)
    organization = session.get(OrganizationModel, organization_id)
    assert organization is not None
    organization.settings = {"locale": "en", "timezone": "America/New_York"}
    session.add(
        BusinessConfigurationModel(
            id=uuid4(),
            bot_id=bot_a1,
            business_name="Legacy support",
            description="PRD-005 compatibility source",
            timezone="America/New_York",
            business_hours={
                day: {
                    "enabled": day == "sunday",
                    "open_time": "09:00",
                    "close_time": "17:00",
                }
                for day in (
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                )
            },
            services=[],
            payment_methods=[],
            policies=[],
            service_instructions="Legacy",
            handoff_keywords=[],
            status="configured",
        )
    )
    session.commit()
    generated_at = datetime(2026, 3, 8, 16, 0, tzinfo=UTC)
    organization_result = _service(session).summary(
        organization_id, actor, period="today", generated_at=generated_at
    )
    assert organization_result.period.from_ == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    assert organization_result.period.to == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)
    assert (
        organization_result.period.to - organization_result.period.from_
        == timedelta(hours=23)
    )
    bot_result = _service(session).summary(
        organization_id,
        actor,
        bot_id=bot_a1,
        period="today",
        generated_at=generated_at,
    )
    assert bot_result.business.status == "open"
    assert bot_result.business.source == "prd_005"
    assert not session.new
    assert not session.dirty
    assert not session.deleted
    assert _business_write_counts(session) == (0, 0)


def test_dashboard_business_resolution_error_is_unknown_and_read_only(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, _foreign_id, _bot_a1, _bot_a2, _actor = _base(session)
    repository = BusinessCalendarRepository(session)
    calendars = BusinessCalendarService(repository, session)

    def fail(_organization_id: UUID) -> BusinessCalendarModel | None:
        raise BusinessCalendarPersistenceError("persistence failed")

    monkeypatch.setattr(repository, "active_default_calendar", fail)
    result = DashboardBusinessStatusReader(
        calendars,
        BusinessHoursStateCompatibilityService(calendars, session),
    ).status(organization_id, None, NOW)

    assert result == DashboardBusinessSummary(
        scope="organization", status="unknown", source="none"
    )
    assert not session.new
    assert not session.dirty
    assert not session.deleted
    assert _business_write_counts(session) == (0, 0)


def _json_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _json_keys(nested)
        }
    if isinstance(value, list):
        return {key for nested in value for key in _json_keys(nested)}
    return set()


def test_dashboard_api_rbac_safe_errors_and_pii_contract(session: Session) -> None:
    organization_id, foreign_id, bot_a1, bot_a2, owner = _base(session)
    foreign_bot = _populate(session, organization_id, foreign_id, bot_a1, bot_a2, owner)
    actors = {"current": owner}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_dashboard_query_service] = lambda: _service(session)
    app.dependency_overrides[require_authenticated_user] = lambda: actors["current"]
    client = TestClient(app)

    roles: tuple[Role, ...] = (
        "viewer",
        "operator",
        "organization_admin",
        "organization_owner",
        "platform_admin",
    )
    response = None
    for role in roles:
        actors["current"] = _actor(organization_id, role)
        response = client.get(
            f"/organizations/{organization_id}/dashboard",
            params={"period": "last_7_days", "bot_id": str(bot_a1)},
        )
        assert response.status_code == 200, response.text
    assert response is not None
    forbidden_keys = {
        "message",
        "message_body",
        "text",
        "phone",
        "email",
        "sender",
        "display_name",
        "notes",
        "external_customer_id",
        "ciphertext",
        "hash",
        "token",
        "secret",
        "authorization",
        "provider_payload",
    }
    assert _json_keys(response.json()).isdisjoint(forbidden_keys)

    invalid = client.get(
        f"/organizations/{organization_id}/dashboard",
        params={"period": "quarter"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "DASHBOARD_INVALID_FILTER"
    missing_bot = client.get(
        f"/organizations/{organization_id}/dashboard",
        params={"bot_id": str(foreign_bot)},
    )
    assert missing_bot.status_code == 404
    assert missing_bot.json()["detail"]["code"] == "DASHBOARD_NOT_FOUND"

    for role in roles[:-1]:
        actors["current"] = _actor(foreign_id, role)
        denied = client.get(f"/organizations/{organization_id}/dashboard")
        assert denied.status_code == 403


@pytest.mark.parametrize("fail_at_select", (1, 2))
def test_dashboard_sqlalchemy_errors_return_only_safe_unavailable_code(
    session: Session, fail_at_select: int
) -> None:
    organization_id, _foreign_id, _bot_a1, _bot_a2, actor = _base(session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_dashboard_query_service] = lambda: _service(session)
    app.dependency_overrides[require_authenticated_user] = lambda: actor
    client = TestClient(app, raise_server_exceptions=False)
    select_count = 0

    def fail_query(
        _connection: Connection,
        _cursor: object,
        _statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal select_count
        select_count += 1
        if select_count == fail_at_select:
            raise SQLAlchemyError("SELECT secret_identifier FROM private_table")

    event.listen(session.get_bind(), "before_cursor_execute", fail_query)
    try:
        response = client.get(f"/organizations/{organization_id}/dashboard")
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", fail_query)

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "DASHBOARD_UNAVAILABLE"}}
    assert "secret_identifier" not in response.text


class _UnknownBusinessReader:
    def status(
        self,
        organization_id: UUID,
        bot_id: UUID | None,
        evaluated_at: datetime,
    ) -> DashboardBusinessSummary:
        del organization_id, evaluated_at
        return DashboardBusinessSummary(
            scope="bot" if bot_id else "organization",
            status="unknown",
            source="none",
        )


def test_performance_sanity_uses_fixed_sql_aggregates_without_orm_hydration(
    session: Session,
) -> None:
    organization_id, _foreign_id, bot_a1, _bot_a2, actor = _base(session)
    session.add_all(
        _conversation(
            organization_id,
            bot_a1,
            "open" if index % 2 else "closed",
            NOW - timedelta(minutes=index % 60),
        )
        for index in range(10_000)
    )
    session.commit()
    statements: list[str] = []

    def capture(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    event.listen(session.get_bind(), "before_cursor_execute", capture)
    try:
        result = DashboardQueryService(
            SqlAlchemyDashboardRepository(session), _UnknownBusinessReader()
        ).summary(organization_id, actor, period="today", generated_at=NOW)
        organization_statements = list(statements)
        statements.clear()
        bot_result = DashboardQueryService(
            SqlAlchemyDashboardRepository(session), _UnknownBusinessReader()
        ).summary(
            organization_id,
            actor,
            bot_id=bot_a1,
            period="today",
            generated_at=NOW,
        )
        bot_statements = list(statements)
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", capture)
    assert result.conversations.total == 10_000
    assert bot_result.conversations.total == 10_000
    assert len(organization_statements) == 7
    assert len(bot_statements) == 8
    conversation_queries = [
        item for item in organization_statements if "from conversation" in item
    ]
    assert len(conversation_queries) == 1
    assert "count(" in conversation_queries[0]
    assert "conversation.id" not in conversation_queries[0].split("from", maxsplit=1)[0]
