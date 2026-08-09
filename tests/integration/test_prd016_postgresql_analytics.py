import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.analytics.service import (
    AnalyticsProjectionService,
    AnalyticsQueryService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.domain.analytics.errors import AnalyticsForbidden, AnalyticsNotFound
from app.domain.user.contracts import User
from app.infrastructure.models.analytics import (
    AnalyticsDailySummaryModel,
    ConversationManagementEventModel,
    HandoffCycleModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.analytics_repository import (
    SqlAlchemyAnalyticsRepository,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationManagementRepository,
)
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("BOTWA_PRD016_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD016_POSTGRES_URL is required for explicit PostgreSQL tests",
)

LOCAL_DAY = date(2026, 8, 8)


def _database_url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _seed(session: Session) -> tuple[UUID, UUID, UUID, UUID, User, User]:
    organization_a, organization_b = uuid4(), uuid4()
    bot_a, bot_b, user_a, user_b = uuid4(), uuid4(), uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_a,
                name="PRD-016 tenant A",
                slug=f"prd016-a-{organization_a}",
                status="active",
                settings={"timezone": "America/New_York"},
            ),
            OrganizationModel(
                id=organization_b,
                name="PRD-016 tenant B",
                slug=f"prd016-b-{organization_b}",
                status="active",
                settings={"timezone": "UTC"},
            ),
        )
    )
    session.flush()
    session.add_all(
        (
            BotModel(
                id=bot_a,
                organization_id=organization_a,
                name="A",
                slug="a",
                status="active",
                created_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
            ),
            BotModel(
                id=bot_b,
                organization_id=organization_b,
                name="B",
                slug="b",
                status="active",
                created_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
            ),
            UserModel(
                id=user_a,
                organization_id=organization_a,
                email=f"{user_a}@prd016.invalid",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
            UserModel(
                id=user_b,
                organization_id=organization_b,
                email=f"{user_b}@prd016.invalid",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
        )
    )
    session.commit()
    actor_a = User(
        id=user_a,
        organization_id=organization_a,
        email=f"{user_a}@prd016.invalid",
        role="organization_owner",
    )
    actor_b = User(
        id=user_b,
        organization_id=organization_b,
        email=f"{user_b}@prd016.invalid",
        role="organization_owner",
    )
    return organization_a, organization_b, bot_a, bot_b, actor_a, actor_b


def _projection(session: Session) -> AnalyticsProjectionService:
    return AnalyticsProjectionService(SqlAlchemyAnalyticsRepository(session))


def test_prd016_postgresql_projection_concurrency_tenant_scope_and_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(_database_url())
    assert engine.dialect.name == "postgresql"
    monkeypatch.setenv("BOTWA_DATABASE_URL", _database_url())
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "20260808_0017")
    inspector = inspect(engine)
    assert {
        "conversation_management_event",
        "handoff_cycle",
        "analytics_daily_summary",
    }.issubset(set(inspector.get_table_names()))
    indexes = {
        item["name"]: item for item in inspector.get_indexes("analytics_daily_summary")
    }
    assert indexes["uq_analytics_daily_summary_bot"]["unique"]
    assert indexes["uq_analytics_daily_summary_organization"]["unique"]

    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        organization_a, organization_b, bot_a, bot_b, actor_a, actor_b = _seed(session)

    barrier = Barrier(2)

    def rebuild() -> None:
        with sessions() as session:
            barrier.wait()
            _projection(session).rebuild_day(organization_a, bot_a, LOCAL_DAY)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: rebuild(), range(2)))

    with sessions() as session:
        assert (
            session.scalar(
                select(func.count(AnalyticsDailySummaryModel.id)).where(
                    AnalyticsDailySummaryModel.organization_id == organization_a,
                    AnalyticsDailySummaryModel.bot_id == bot_a,
                    AnalyticsDailySummaryModel.local_date == LOCAL_DAY,
                )
            )
            == 1
        )
        projection = _projection(session)
        projection.rebuild_day(organization_a, None, LOCAL_DAY)
        projection.rebuild_day(organization_b, bot_b, LOCAL_DAY)
        projection.rebuild_day(organization_b, None, LOCAL_DAY)
        query = AnalyticsQueryService(SqlAlchemyAnalyticsRepository(session))
        result = query.query(
            organization_a,
            actor_a,
            bot_id=bot_a,
            from_=LOCAL_DAY,
            to=LOCAL_DAY + timedelta(days=1),
            group_by="day",
            compare=None,
        )
        assert result.complete is True
        assert result.reporting_timezone == "America/New_York"
        original_summary = result.summary
        session.add(
            BotModel(
                organization_id=organization_a,
                name="Late historical bot",
                slug="late-historical-bot",
                status="inactive",
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )
        session.commit()
        unchanged = query.query(
            organization_a,
            actor_a,
            bot_id=None,
            from_=LOCAL_DAY,
            to=LOCAL_DAY + timedelta(days=1),
            group_by="day",
            compare=None,
        )
        assert unchanged.complete is True
        assert unchanged.summary == original_summary
        csv = query.export_csv(
            organization_a,
            actor_a,
            bot_id=bot_a,
            from_=LOCAL_DAY,
            to=LOCAL_DAY + timedelta(days=1),
            group_by="day",
        )
        assert "period_start,period_end" in csv
        assert "conversation_id" not in csv
        with pytest.raises(AnalyticsForbidden):
            query.query(
                organization_b,
                actor_a,
                bot_id=None,
                from_=LOCAL_DAY,
                to=LOCAL_DAY + timedelta(days=1),
                group_by="day",
                compare=None,
            )
        with pytest.raises(AnalyticsNotFound):
            query.query(
                organization_b,
                actor_b,
                bot_id=bot_a,
                from_=LOCAL_DAY,
                to=LOCAL_DAY + timedelta(days=1),
                group_by="day",
                compare=None,
            )

        handoff_conversation = ConversationModel(
            company_id=str(organization_a),
            customer_id="handoff-cycle",
            organization_id=organization_a,
            bot_id=bot_a,
            management_status="open",
            channel="whatsapp",
            status="active",
        )
        session.add(handoff_conversation)
        session.commit()
        handoff = HumanHandoffService(
            HumanHandoffRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
        )
        handoff.request(organization_a, handoff_conversation.id, actor_a, "postgresql")
        handoff.claim(organization_a, handoff_conversation.id, actor_a)
        handoff.resolve(
            organization_a,
            handoff_conversation.id,
            actor_a,
            return_to_bot=True,
        )
        cycle = session.scalar(
            select(HandoffCycleModel).where(
                HandoffCycleModel.conversation_id == handoff_conversation.id
            )
        )
        assert cycle is not None
        assert cycle.resolution_type == "returned_to_bot"
        assert cycle.activated_at is not None
        assert cycle.resolved_at is not None

        conversation = ConversationModel(
            company_id=str(organization_a),
            customer_id="rollback",
            organization_id=organization_a,
            bot_id=bot_a,
            management_status="open",
            channel="whatsapp",
            status="active",
        )
        session.add(conversation)
        session.commit()
        occurred_at = result.source_watermark_at
        assert occurred_at is not None
        repository = SqlAlchemyConversationManagementRepository(session)
        repository.transition(conversation, "closed", occurred_at)
        session.add(
            ConversationManagementEventModel(
                organization_id=organization_a,
                conversation_id=conversation.id,
                bot_id=bot_a,
                from_status="open",
                to_status="closed",
                occurred_at=occurred_at,
                actor_type="user",
                actor_id=actor_a.id,
            )
        )
        session.flush()
        session.rollback()
        session.refresh(conversation)
        assert conversation.management_status == "open"
        assert (
            session.scalar(
                select(func.count(ConversationManagementEventModel.id)).where(
                    ConversationManagementEventModel.conversation_id == conversation.id
                )
            )
            == 0
        )
    engine.dispose()


def test_prd016_alembic_upgrade_downgrade_and_reupgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTWA_DATABASE_URL", _database_url())
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    try:
        command.downgrade(configuration, "20260808_0016")
        engine = create_engine(_database_url())
        assert "analytics_daily_summary" not in inspect(engine).get_table_names()
        assert "business_calendar" in inspect(engine).get_table_names()
        engine.dispose()
        command.upgrade(configuration, "20260808_0017")
        upgraded = create_engine(_database_url())
        assert "analytics_daily_summary" in inspect(upgraded).get_table_names()
        upgraded.dispose()
    finally:
        get_settings.cache_clear()
