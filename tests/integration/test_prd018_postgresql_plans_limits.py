import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.plans.service import PlanEnforcementService
from app.domain.plans.errors import PlanLimitReached
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("BOTWA_PRD018_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD018_POSTGRES_URL is required for explicit PostgreSQL tests",
)
DEFAULT_PLAN_ID = UUID("01800000-0000-0000-0000-000000000001")


def _url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _alembic(revision: str) -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), revision)


def _configuration(limit: int | None) -> dict[str, object]:
    active_bots: dict[str, object] = (
        {"kind": "unlimited"} if limit is None else {"kind": "limited", "value": limit}
    )
    return {
        "features": {
            "analytics": True,
            "analytics_export": True,
            "audit": True,
            "integrations": True,
            "automations": True,
            "human_handoff": True,
            "business_calendar": True,
            "knowledge": True,
            "whatsapp_configuration": True,
        },
        "limits": {
            "max_active_bots": active_bots,
            "max_active_users": {"kind": "unlimited"},
            "max_integrations": {"kind": "unlimited"},
            "max_automations": {"kind": "unlimited"},
            "max_business_calendars": {"kind": "unlimited"},
            "max_whatsapp_configurations": {"kind": "unlimited"},
            "max_knowledge_entries": {"kind": "unlimited"},
        },
    }


def _organization(session: Session, slug: str) -> UUID:
    organization_id = uuid4()
    session.add(
        OrganizationModel(
            id=organization_id,
            name=slug,
            slug=f"{slug}-{organization_id.hex[:8]}",
            status="active",
            settings={},
        )
    )
    session.commit()
    return organization_id


def _restricted_plan(session: Session, limit: int) -> UUID:
    plan_id = uuid4()
    session.add(
        PlanDefinitionModel(
            id=plan_id,
            plan_code=f"restricted-{plan_id.hex[:8]}",
            display_name="Restricted",
            status="active",
            configuration=_configuration(limit),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()
    return plan_id


def test_prd018_postgresql_schema_seed_backfill_and_constraints() -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "20260808_0018")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine)
    with factory() as session:
        existing = _organization(session, "prd018-backfill")
    command.upgrade(configuration, "20260810_0019")
    inspector = inspect(engine)
    assert {"plan_definition", "organization_plan_assignment"} <= set(
        inspector.get_table_names()
    )
    with factory() as session:
        default = session.get(PlanDefinitionModel, DEFAULT_PLAN_ID)
        assignment = session.get(OrganizationPlanAssignmentModel, existing)
        assert default is not None and default.plan_code == "default"
        assert default.configuration == _configuration(None)
        assert assignment is not None
        assert assignment.plan_definition_id == DEFAULT_PLAN_ID
        assert assignment.version == 1
    engine.dispose()


def test_prd018_postgresql_capacity_and_plan_change_are_serialized() -> None:
    _alembic("20260810_0019")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as seed:
        organization_id = _organization(seed, "prd018-lock")
        restricted_id = _restricted_plan(seed, 1)
        seed.add(
            OrganizationPlanAssignmentModel(
                organization_id=organization_id,
                plan_definition_id=restricted_id,
                version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        seed.commit()

    first_locked = Event()
    release_first = Event()

    def first_create() -> str:
        with factory() as session:
            enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
            enforcement.require_consuming_action(
                organization_id, limit="max_active_bots"
            )
            session.add(
                BotModel(
                    organization_id=organization_id,
                    name="First",
                    slug="first",
                    status="active",
                    settings={},
                )
            )
            session.flush()
            first_locked.set()
            assert release_first.wait(10)
            session.commit()
            return "created"

    def second_create() -> str:
        assert first_locked.wait(10)
        with factory() as session:
            enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
            try:
                enforcement.require_consuming_action(
                    organization_id, limit="max_active_bots"
                )
            except PlanLimitReached:
                return "denied"
            return "unexpected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_create)
        second = executor.submit(second_create)
        assert first_locked.wait(10)
        release_first.set()
        assert first.result(timeout=15) == "created"
        assert second.result(timeout=15) == "denied"

    with factory() as session:
        assignment = session.get(OrganizationPlanAssignmentModel, organization_id)
        assert assignment is not None
        lower_plan = _restricted_plan(session, 0)

    plan_locked = Event()
    release_plan = Event()

    def lower_plan_transaction() -> None:
        with factory() as session:
            repository = SqlAlchemyPlanRepository(session)
            assert repository.lock_organization(organization_id)
            row = repository.assignment_model(organization_id)
            assert row is not None
            row.plan_definition_id = lower_plan
            row.version += 1
            plan_locked.set()
            assert release_plan.wait(10)
            session.commit()

    def create_again() -> str:
        assert plan_locked.wait(10)
        with factory() as session:
            enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
            try:
                enforcement.require_consuming_action(
                    organization_id, limit="max_active_bots"
                )
            except PlanLimitReached:
                return "denied_after_downgrade"
            return "unexpected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        changed = executor.submit(lower_plan_transaction)
        created = executor.submit(create_again)
        assert plan_locked.wait(10)
        release_plan.set()
        changed.result(timeout=15)
        assert created.result(timeout=15) == "denied_after_downgrade"
    engine.dispose()


def test_prd018_postgresql_migration_cycle_single_head() -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "20260810_0019")
    command.downgrade(configuration, "20260808_0018")
    command.upgrade(configuration, "20260810_0019")
    engine = create_engine(_url())
    try:
        assert {"plan_definition", "organization_plan_assignment"} <= set(
            inspect(engine).get_table_names()
        )
        with engine.connect() as connection:
            assert connection.scalar(select(PlanDefinitionModel.plan_code)) == "default"
    finally:
        engine.dispose()
