from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.api.analytics_dependencies import get_analytics_query_service
from app.api.analytics_routes import router as analytics_router
from app.api.dependencies import require_authenticated_user
from app.application.analytics.service import (
    AnalyticsProjectionService,
    AnalyticsQueryService,
)
from app.domain.access.contracts import Role
from app.domain.analytics.errors import (
    AnalyticsForbidden,
    AnalyticsNotFound,
    AnalyticsRangeTooLarge,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.analytics import (
    AnalyticsDailySummaryModel,
    ConversationManagementEventModel,
    HandoffCycleModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.analytics_repository import (
    SqlAlchemyAnalyticsRepository,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.plan_support import allow_all_plan_enforcement

DAY = date(2026, 8, 8)
NOON = datetime(2026, 8, 8, 12, tzinfo=UTC)


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
        email=f"analytics-{uuid4()}@example.invalid",
        role=role,
    )


def _base(session: Session) -> tuple[UUID, UUID, UUID, UUID, User]:
    organization_id, foreign_id = uuid4(), uuid4()
    bot_a, bot_a2, bot_b, user_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Tenant A",
                slug=f"a-{organization_id}",
                status="active",
                settings={"timezone": "UTC"},
            ),
            OrganizationModel(
                id=foreign_id,
                name="Tenant B",
                slug=f"b-{foreign_id}",
                status="active",
                settings={"timezone": "UTC"},
            ),
            BotModel(
                id=bot_a,
                organization_id=organization_id,
                name="A1",
                slug="a1",
                status="active",
                timezone="Pacific/Auckland",
                created_at=NOON,
            ),
            BotModel(
                id=bot_a2,
                organization_id=organization_id,
                name="A2",
                slug="a2",
                status="active",
                timezone="America/New_York",
                created_at=NOON,
            ),
            BotModel(
                id=bot_b,
                organization_id=foreign_id,
                name="B",
                slug="b",
                status="active",
                created_at=NOON,
            ),
            UserModel(
                id=user_id,
                organization_id=organization_id,
                email=f"{user_id}@example.invalid",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
        )
    )
    session.commit()
    actor = User(
        id=user_id,
        organization_id=organization_id,
        email=f"{user_id}@example.invalid",
        role="organization_owner",
    )
    return organization_id, foreign_id, bot_a, bot_a2, actor


def _seed_sources(
    session: Session, organization_id: UUID, bot_id: UUID, actor_id: UUID
) -> ManagedAutomationExecutionModel:
    conversation_id, handoff_id = uuid4(), uuid4()
    definition_id, receipt_id = uuid4(), uuid4()
    session.add_all(
        (
            ConversationModel(
                id=conversation_id,
                company_id=str(organization_id),
                customer_id="masked",
                organization_id=organization_id,
                bot_id=bot_id,
                management_status="closed",
                channel="whatsapp",
                status="active",
                started_at=NOON,
                created_at=NOON,
                updated_at=NOON,
            ),
            ConversationManagementEventModel(
                organization_id=organization_id,
                conversation_id=conversation_id,
                bot_id=bot_id,
                from_status="open",
                to_status="closed",
                occurred_at=NOON + timedelta(minutes=1),
                actor_type="user",
                actor_id=actor_id,
            ),
            HandoffSessionModel(
                id=handoff_id,
                conversation_id=conversation_id,
                organization_id=organization_id,
                bot_id=bot_id,
                status="resolved",
                requested_at=NOON,
                resolved_at=NOON + timedelta(seconds=90),
                last_activity_at=NOON + timedelta(seconds=90),
            ),
            ContactModel(
                organization_id=organization_id,
                channel_type="whatsapp",
                external_identifier_hash=f"hash-{uuid4()}",
                external_identifier_ciphertext="secret-phone",
                created_at=NOON,
                updated_at=NOON,
            ),
            ManagedAutomationDefinitionModel(
                id=definition_id,
                organization_id=organization_id,
                bot_id=bot_id,
                name="Handoff",
                trigger_type="conversation.inbound_received",
                conditions_data={},
                action_type="request_handoff",
                action_data={"reason_code": "automation_rule"},
                status="active",
                version=1,
                created_by_user_id=actor_id,
                updated_by_user_id=actor_id,
                created_at=NOON,
                updated_at=NOON,
            ),
            ManagedAutomationEventReceiptModel(
                id=receipt_id,
                organization_id=organization_id,
                bot_id=bot_id,
                source_type="conversation",
                source_event_id=uuid4(),
                event_type="conversation.inbound_received",
                event_data={},
                correlation_id=uuid4(),
                occurred_at=NOON,
                created_at=NOON,
            ),
        )
    )
    session.flush()
    session.add(
        HandoffCycleModel(
            organization_id=organization_id,
            conversation_id=conversation_id,
            bot_id=bot_id,
            handoff_session_id=handoff_id,
            requested_at=NOON,
            activated_at=NOON + timedelta(seconds=10),
            resolved_at=NOON + timedelta(seconds=90),
            resolution_type="returned_to_bot",
        )
    )
    execution = ManagedAutomationExecutionModel(
        organization_id=organization_id,
        automation_definition_id=definition_id,
        definition_version=1,
        event_receipt_id=receipt_id,
        definition_snapshot={},
        event_snapshot={},
        status="failed",
        attempt_count=3,
        available_at=NOON,
        completed_at=NOON + timedelta(minutes=2),
        correlation_id=uuid4(),
        created_at=NOON,
        updated_at=NOON,
    )
    session.add(execution)
    session.commit()
    return execution


def _services(
    session: Session,
) -> tuple[AnalyticsProjectionService, AnalyticsQueryService]:
    repository = SqlAlchemyAnalyticsRepository(session)
    return AnalyticsProjectionService(repository), AnalyticsQueryService(
        repository, plan_enforcement=allow_all_plan_enforcement()
    )


def _bot(session: Session, bot_id: UUID) -> BotModel:
    model = session.get(BotModel, bot_id)
    assert model is not None
    return model


def test_projection_is_idempotent_and_uses_current_automation_outcome(
    session: Session,
) -> None:
    organization_id, _, bot_id, _, actor = _base(session)
    execution = _seed_sources(session, organization_id, bot_id, actor.id)
    projection, query = _services(session)
    projection.rebuild_day(organization_id, bot_id, DAY)
    projection.rebuild_day(organization_id, None, DAY)
    projection.rebuild_day(organization_id, bot_id, DAY)
    assert session.scalar(select(func.count(AnalyticsDailySummaryModel.id))) == 2

    response = query.query(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert response.complete is True
    assert response.reporting_timezone == "UTC"
    assert response.summary.conversations_started == 1
    assert response.summary.conversations_closed == 1
    assert response.summary.handoffs_created == 1
    assert response.summary.handoffs_resolved == 1
    assert response.summary.handoff_average_resolution_seconds == 90
    assert response.summary.automation_executions_created == 1
    assert response.summary.automation_failed == 1
    assert response.summary.contacts_created == 1

    execution.status = "succeeded"
    execution.completed_at = NOON + timedelta(minutes=3)
    session.commit()
    projection.rebuild_day(organization_id, bot_id, DAY)
    corrected = query.query(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert corrected.summary.automation_failed == 0
    assert corrected.summary.automation_succeeded == 1
    assert corrected.summary.automation_executions_created == 1


def test_organization_scope_requires_every_bot_and_never_attributes_contacts(
    session: Session,
) -> None:
    organization_id, _, bot_a, bot_a2, actor = _base(session)
    _seed_sources(session, organization_id, bot_a, actor.id)
    projection, query = _services(session)
    projection.rebuild_day(organization_id, bot_a, DAY)
    projection.rebuild_day(organization_id, None, DAY)
    incomplete = query.query(
        organization_id,
        actor,
        bot_id=None,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert incomplete.complete is False
    projection.rebuild_day(organization_id, bot_a2, DAY)
    complete = query.query(
        organization_id,
        actor,
        bot_id=None,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert complete.complete is True
    assert complete.contacts_scope == "organization"
    assert complete.summary.contacts_created == 1
    assert complete.summary.conversations_started == 1


def test_analytics_historical_completeness_ignores_bots_created_after_bucket(
    session: Session,
) -> None:
    organization_id, _, bot_a, bot_a2, actor = _base(session)
    historical_day = DAY - timedelta(days=10)
    _bot(session, bot_a).created_at = datetime.combine(
        historical_day - timedelta(days=1), datetime.min.time(), UTC
    )
    _bot(session, bot_a2).created_at = datetime.combine(
        historical_day + timedelta(days=5), datetime.min.time(), UTC
    )
    session.commit()
    projection, query = _services(session)
    projection.rebuild_day(organization_id, bot_a, historical_day)
    projection.rebuild_day(organization_id, None, historical_day)
    before = query.query(
        organization_id,
        actor,
        bot_id=None,
        from_=historical_day,
        to=historical_day + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert before.complete is True
    session.add(
        BotModel(
            organization_id=organization_id,
            name="Late bot",
            slug="late-bot",
            status="inactive",
            created_at=datetime.combine(
                historical_day + timedelta(days=20), datetime.min.time(), UTC
            ),
        )
    )
    session.commit()
    after = query.query(
        organization_id,
        actor,
        bot_id=None,
        from_=historical_day,
        to=historical_day + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert after.complete is True
    assert after.summary == before.summary


def test_analytics_bot_created_mid_range_only_affects_expected_later_buckets(
    session: Session,
) -> None:
    organization_id, _, bot_a, bot_a2, actor = _base(session)
    start = DAY - timedelta(days=2)
    _bot(session, bot_a).created_at = datetime.combine(
        start + timedelta(days=1), datetime.min.time(), UTC
    ) + timedelta(hours=12)
    _bot(session, bot_a2).created_at = datetime.combine(
        start + timedelta(days=5), datetime.min.time(), UTC
    )
    session.commit()
    projection, query = _services(session)
    for offset in range(3):
        projection.rebuild_day(organization_id, None, start + timedelta(days=offset))
    first = projection.rebuild_day(organization_id, bot_a, start)
    projection.rebuild_day(organization_id, bot_a, start + timedelta(days=2))
    incomplete = query.query(
        organization_id,
        actor,
        bot_id=None,
        from_=start,
        to=start + timedelta(days=3),
        group_by="day",
        compare=None,
    )
    assert first.written is False
    assert incomplete.complete is False
    projection.rebuild_day(organization_id, bot_a, start + timedelta(days=1))
    complete = query.query(
        organization_id,
        actor,
        bot_id=None,
        from_=start,
        to=start + timedelta(days=3),
        group_by="day",
        compare=None,
    )
    assert complete.complete is True
    stored_days = session.scalars(
        select(AnalyticsDailySummaryModel.local_date).where(
            AnalyticsDailySummaryModel.organization_id == organization_id,
            AnalyticsDailySummaryModel.bot_id == bot_a,
        )
    ).all()
    assert start not in stored_days


def test_bot_scoped_history_before_creation_does_not_require_fake_rows(
    session: Session,
) -> None:
    organization_id, _, bot_id, _, actor = _base(session)
    start = DAY - timedelta(days=3)
    _bot(session, bot_id).created_at = datetime.combine(
        DAY + timedelta(days=10), datetime.min.time(), UTC
    )
    session.commit()
    projection, query = _services(session)
    for offset in range(2):
        projection.rebuild_day(organization_id, None, start + timedelta(days=offset))
    results = projection.rebuild_range(
        organization_id, bot_id, start, start + timedelta(days=2)
    )
    response = query.query(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=start,
        to=start + timedelta(days=2),
        group_by="day",
        compare=None,
    )
    assert all(result.written is False for result in results)
    assert response.complete is True
    assert response.summary.conversations_started == 0
    assert (
        session.scalar(
            select(func.count(AnalyticsDailySummaryModel.id)).where(
                AnalyticsDailySummaryModel.organization_id == organization_id,
                AnalyticsDailySummaryModel.bot_id == bot_id,
            )
        )
        == 0
    )


def test_bot_analytics_requires_organization_contact_rows_for_complete_response(
    session: Session,
) -> None:
    organization_id, _, bot_id, _, actor = _base(session)
    projection, query = _services(session)
    projection.rebuild_day(organization_id, bot_id, DAY)
    missing_contact = query.query(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert missing_contact.complete is False
    projection.rebuild_day(organization_id, None, DAY)
    with_contact_zero = query.query(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="day",
        compare=None,
    )
    assert with_contact_zero.complete is True
    assert with_contact_zero.summary.contacts_created == 0


def test_previous_period_grouping_csv_rbac_and_no_pii(session: Session) -> None:
    organization_id, _, bot_id, _, actor = _base(session)
    _seed_sources(session, organization_id, bot_id, actor.id)
    projection, query = _services(session)
    for local_day in (DAY - timedelta(days=1), DAY):
        projection.rebuild_day(organization_id, bot_id, local_day)
        projection.rebuild_day(organization_id, None, local_day)
    response = query.query(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="week",
        compare="previous_period",
    )
    assert response.complete is True
    assert response.comparison is not None
    assert response.comparison.change["conversations_started"].percent_change is None
    csv = query.export_csv(
        organization_id,
        actor,
        bot_id=bot_id,
        from_=DAY,
        to=DAY + timedelta(days=1),
        group_by="month",
    )
    assert "period_start,period_end" in csv
    assert "secret-phone" not in csv
    assert "conversation_id" not in csv
    with pytest.raises(AnalyticsForbidden):
        query.export_csv(
            organization_id,
            _actor(organization_id, "viewer"),
            bot_id=bot_id,
            from_=DAY,
            to=DAY + timedelta(days=1),
            group_by="day",
        )


def test_timezone_dst_range_and_tenant_isolation(session: Session) -> None:
    organization_id, foreign_id, bot_id, _, actor = _base(session)
    projection, query = _services(session)
    spring_start, spring_end = projection._bucket("America/New_York", date(2026, 3, 8))
    fall_start, fall_end = projection._bucket("America/New_York", date(2026, 11, 1))
    assert spring_end - spring_start == timedelta(hours=23)
    assert fall_end - fall_start == timedelta(hours=25)
    assert projection._range_days(date(2024, 1, 1), date(2025, 1, 1)) == 366
    with pytest.raises(AnalyticsRangeTooLarge):
        projection._range_days(date(2024, 1, 1), date(2025, 1, 2))
    with pytest.raises(AnalyticsForbidden):
        query.query(
            foreign_id,
            actor,
            bot_id=None,
            from_=DAY,
            to=DAY + timedelta(days=1),
            group_by="day",
            compare=None,
        )
    foreign_actor = _actor(foreign_id)
    with pytest.raises(AnalyticsNotFound) as exc_info:
        query.query(
            foreign_id,
            foreign_actor,
            bot_id=bot_id,
            from_=DAY,
            to=DAY + timedelta(days=1),
            group_by="day",
            compare=None,
        )
    assert getattr(exc_info.value, "safe_code", None) == "ANALYTICS_NOT_FOUND"


def test_analytics_api_rbac_and_csv_contract(session: Session) -> None:
    organization_id, _, bot_id, _, owner = _base(session)
    _seed_sources(session, organization_id, bot_id, owner.id)
    projection, query = _services(session)
    projection.rebuild_day(organization_id, bot_id, DAY)
    projection.rebuild_day(organization_id, None, DAY)
    app = FastAPI()
    app.include_router(analytics_router)
    app.dependency_overrides[get_analytics_query_service] = lambda: query
    viewer = _actor(organization_id, "viewer")
    app.dependency_overrides[require_authenticated_user] = lambda: viewer
    client = TestClient(app)
    base = f"/organizations/{organization_id}/analytics"
    params = {
        "bot_id": str(bot_id),
        "from": DAY.isoformat(),
        "to": (DAY + timedelta(days=1)).isoformat(),
        "group_by": "day",
    }
    response = client.get(base, params=params)
    assert response.status_code == 200
    assert response.json()["contacts_scope"] == "organization"
    assert client.get(f"{base}/export", params=params).status_code == 403
    app.dependency_overrides[require_authenticated_user] = lambda: owner
    exported = client.get(f"{base}/export", params=params)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "phone" not in exported.text


def test_migration_declares_only_prd016_tables_and_partial_uniqueness() -> None:
    source = (
        __import__("pathlib")
        .Path("alembic/versions/20260808_0017_create_analytics_reports.py")
        .read_text(encoding="utf-8")
    )
    assert 'revision = "20260808_0017"' in source
    assert 'down_revision = "20260808_0016"' in source
    assert '"conversation_management_event"' in source
    assert '"handoff_cycle"' in source
    assert '"analytics_daily_summary"' in source
    assert 'postgresql_where=sa.text("bot_id IS NULL")' in source
    assert 'postgresql_where=sa.text("bot_id IS NOT NULL")' in source
    assert "report_job" not in source


def test_source_watermark_is_documented_as_cutoff_not_snapshot() -> None:
    documentation = (
        __import__("pathlib")
        .Path("docs/PRD-016-analytics-reports.md")
        .read_text(encoding="utf-8")
    )
    assert "upper source-time cutoff" in documentation
    assert "not a transactional snapshot" in documentation
