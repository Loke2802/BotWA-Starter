import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.onboarding.readiness import OnboardingReadinessService
from app.application.onboarding.service import OnboardingService
from app.domain.audit.contracts import AuditEventDraft
from app.domain.audit.ports import AuditWriter
from app.domain.plans.contracts import PlanConfiguration
from app.domain.user.contracts import User
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel
from app.infrastructure.models.onboarding import OrganizationOnboardingModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.onboarding_repository import (
    SqlAlchemyOnboardingRepository,
)
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("BOTWA_PRD020_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD020_POSTGRES_URL is required for explicit PostgreSQL tests",
)


def _url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _alembic(revision: str) -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), revision)


def _configuration() -> PlanConfiguration:
    return PlanConfiguration.model_validate(
        {
            "features": {
                "analytics": True,
                "analytics_export": True,
                "audit": True,
                "integrations": True,
                "automations": True,
                "human_handoff": True,
                "business_calendar": True,
                "knowledge": True,
                "whatsapp_configuration": False,
            },
            "limits": {
                "max_active_bots": {"kind": "unlimited"},
                "max_active_users": {"kind": "unlimited"},
                "max_integrations": {"kind": "unlimited"},
                "max_automations": {"kind": "unlimited"},
                "max_business_calendars": {"kind": "unlimited"},
                "max_whatsapp_configurations": {"kind": "unlimited"},
                "max_knowledge_entries": {"kind": "unlimited"},
            },
        }
    )


def _seed(session: Session, *, ready: bool = False) -> tuple[UUID, User]:
    now = datetime.now(UTC)
    organization_id, user_id, plan_id = uuid4(), uuid4(), uuid4()
    organization = OrganizationModel(
        id=organization_id,
        name="PRD-020 PostgreSQL",
        slug=f"prd020-{organization_id.hex[:10]}",
        status="active",
        settings={"locale": "es", "timezone": "America/Lima"},
        created_at=now,
        updated_at=now,
    )
    plan = PlanDefinitionModel(
        id=plan_id,
        plan_code=f"prd020-{plan_id.hex[:10]}",
        display_name="PRD-020",
        status="active",
        configuration=_configuration().model_dump(mode="json"),
        created_at=now,
        updated_at=now,
    )
    user = UserModel(
        id=user_id,
        organization_id=organization_id,
        email=f"prd020-{user_id}@example.invalid",
        password_hash="hash",
        role="organization_owner",
        status="active",
        auth_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add_all([organization, plan])
    session.flush()
    session.add_all(
        [
            user,
            OrganizationPlanAssignmentModel(
                organization_id=organization_id,
                plan_definition_id=plan_id,
                version=1,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    if ready:
        bot = BotModel(
            organization_id=organization_id,
            name="PRD-020 Bot",
            slug=f"prd020-{uuid4().hex[:10]}",
            status="active",
            settings={},
            created_at=now,
            updated_at=now,
        )
        session.add(bot)
        session.flush()
        closed = {"enabled": False, "open_time": None, "close_time": None}
        hours = {
            day: dict(closed)
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        }
        session.add(
            BusinessConfigurationModel(
                bot_id=bot.id,
                business_name="Luri",
                description="Ready",
                timezone="America/Lima",
                business_hours=hours,
                services=[{"name": "Support", "active": True}],
                payment_methods=["cash"],
                policies=[],
                service_instructions="Ready",
                handoff_enabled=False,
                handoff_keywords=[],
                handoff_outside_business_hours=False,
                status="configured",
                created_at=now,
                updated_at=now,
            )
        )
    session.commit()
    return organization_id, User(
        id=user_id,
        organization_id=organization_id,
        email="owner@example.invalid",
        role="organization_owner",
    )


def _service(session: Session, writer: AuditWriter | None = None) -> OnboardingService:
    repository = SqlAlchemyOnboardingRepository(session)
    return OnboardingService(
        repository,
        OnboardingReadinessService(repository),
        session,
        writer or SqlAlchemyAuditRepository(session),
    )


def test_prd020_migration_cycle_schema_constraints_and_legacy() -> None:
    _alembic("20260812_0020")
    _alembic("20260813_0021")
    _alembic("20260812_0020")
    _alembic("20260813_0021")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        assert "organization_onboarding" in inspect(engine).get_table_names()
        with factory() as session:
            organization_id, actor = _seed(session)
            assert session.get(OrganizationOnboardingModel, organization_id) is None
            legacy = _service(session).get(organization_id, actor)
            assert legacy.workflow_status == "not_started"
            session.add(
                OrganizationOnboardingModel(
                    organization_id=organization_id,
                    status="completed",
                    started_at=datetime.now(UTC),
                    started_by_user_id=actor.id,
                    version=1,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        engine.dispose()


def test_prd020_concurrent_start_and_complete_are_single_effects() -> None:
    _alembic("20260813_0021")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        organization_id, actor = _seed(session, ready=True)
    start_barrier = Barrier(2)

    def start() -> tuple[str, int | None]:
        with factory() as session:
            start_barrier.wait(timeout=10)
            response = _service(session).start(organization_id, actor)
            return response.workflow_status, response.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        starts = [executor.submit(start) for _ in range(2)]
        assert [item.result(timeout=20) for item in starts] == [
            ("in_progress", 1),
            ("in_progress", 1),
        ]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(OrganizationOnboardingModel.organization_id)).where(
                    OrganizationOnboardingModel.organization_id == organization_id
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(AuditEventModel.id)).where(
                    AuditEventModel.organization_id == organization_id,
                    AuditEventModel.action == "onboarding.started",
                )
            )
            == 1
        )
    complete_barrier = Barrier(2)

    def complete() -> tuple[str, int | None]:
        with factory() as session:
            complete_barrier.wait(timeout=10)
            response = _service(session).complete(organization_id, 1, actor)
            return response.workflow_status, response.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        completions = [executor.submit(complete) for _ in range(2)]
        assert [item.result(timeout=20) for item in completions] == [
            ("completed", 2),
            ("completed", 2),
        ]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(AuditEventModel.id)).where(
                    AuditEventModel.organization_id == organization_id,
                    AuditEventModel.action == "onboarding.completed",
                )
            )
            == 1
        )
    engine.dispose()


def test_prd020_audit_rollback_and_tenant_isolation() -> None:
    _alembic("20260813_0021")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    class FailingWriter:
        def append(self, draft: AuditEventDraft) -> None:
            raise RuntimeError("audit unavailable")

    with factory() as session:
        organization_id, actor = _seed(session, ready=True)
        with pytest.raises(RuntimeError):
            _service(session, FailingWriter()).start(organization_id, actor)
        assert session.get(OrganizationOnboardingModel, organization_id) is None
        healthy = _service(session)
        healthy.start(organization_id, actor)
        with pytest.raises(RuntimeError):
            _service(session, FailingWriter()).complete(organization_id, 1, actor)
        workflow = session.get(OrganizationOnboardingModel, organization_id)
        assert workflow is not None and workflow.status == "in_progress"
        other_id, other_actor = _seed(session)
        with pytest.raises(ValueError, match="access denied"):
            healthy.get(other_id, actor)
        assert healthy.get(other_id, other_actor).organization_id == other_id
    engine.dispose()
