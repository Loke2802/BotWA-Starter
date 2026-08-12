import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.business_calendar.service import BusinessCalendarService
from app.domain.business_calendar.contracts import (
    BusinessCalendarCreate,
    DateExceptionCreate,
    LocalTimeInterval,
    WeeklyDayInput,
    WeeklyScheduleReplace,
)
from app.domain.business_calendar.errors import (
    BusinessCalendarConflict,
    BusinessCalendarNotFound,
    ScheduleVersionConflict,
)
from app.domain.user.contracts import User
from app.infrastructure.models.business_calendar import (
    BusinessCalendarAuditEventModel,
    BusinessCalendarIdempotencyReceiptModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from tests.plan_support import allow_all_plan_enforcement

DATABASE_URL = os.getenv("BOTWA_PRD015_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD015_POSTGRES_URL is required for explicit PostgreSQL tests",
)


def _database_url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _seed(session: Session) -> tuple[User, User, UUID, UUID]:
    organization_id, foreign_organization_id = uuid4(), uuid4()
    actor = User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"prd015-owner-{uuid4()}@smoke.invalid",
        role="organization_owner",
    )
    foreign_actor = User(
        id=uuid4(),
        organization_id=foreign_organization_id,
        email=f"prd015-foreign-{uuid4()}@smoke.invalid",
        role="organization_owner",
    )
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="PRD-015 tenant A",
                slug=f"prd015-a-{str(organization_id)[:8]}",
                status="active",
            ),
            OrganizationModel(
                id=foreign_organization_id,
                name="PRD-015 tenant B",
                slug=f"prd015-b-{str(foreign_organization_id)[:8]}",
                status="active",
            ),
            UserModel(
                id=actor.id,
                organization_id=organization_id,
                email=actor.email,
                password_hash="x",
                role=actor.role,
                status="active",
            ),
            UserModel(
                id=foreign_actor.id,
                organization_id=foreign_organization_id,
                email=foreign_actor.email,
                password_hash="x",
                role=foreign_actor.role,
                status="active",
            ),
        )
    )
    session.commit()
    return actor, foreign_actor, organization_id, foreign_organization_id


def _service(session: Session) -> BusinessCalendarService:
    return BusinessCalendarService(
        BusinessCalendarRepository(session),
        session,
        SqlAlchemyAuditRepository(session),
        plan_enforcement=allow_all_plan_enforcement(),
    )


def test_prd015_postgresql_constraints_tenant_scope_and_atomicity() -> None:
    engine = create_engine(_database_url())
    assert engine.dialect.name == "postgresql"
    expected_tables = {
        "business_calendar",
        "business_calendar_weekly_interval",
        "business_calendar_date_exception",
        "business_calendar_holiday",
        "business_calendar_override",
        "business_calendar_idempotency_receipt",
        "business_calendar_audit_event",
    }
    assert expected_tables.issubset(set(inspect(engine).get_table_names()))
    calendar_indexes = {
        item["name"]: item for item in inspect(engine).get_indexes("business_calendar")
    }
    assert calendar_indexes["uq_business_calendar_active_org_default"]["unique"]
    assert calendar_indexes["uq_business_calendar_active_org_bot"]["unique"]
    sessions = sessionmaker(bind=engine)

    with sessions() as session:
        actor, foreign_actor, organization_id, foreign_organization_id = _seed(session)
        service = _service(session)
        created = service.create_calendar(
            organization_id,
            BusinessCalendarCreate(name="Support", timezone="America/Lima"),
            actor,
            idempotency_key="postgres-calendar-001",
        )
        foreign = service.create_calendar(
            foreign_organization_id,
            BusinessCalendarCreate(name="Support", timezone="America/Lima"),
            foreign_actor,
            idempotency_key="postgres-calendar-001",
        )
        assert foreign.id != created.id
        with pytest.raises(BusinessCalendarNotFound):
            service.get_calendar(foreign_organization_id, created.id, foreign_actor)

        service.transition_calendar(organization_id, created.id, "activate", actor)
        conflicting = service.create_calendar(
            organization_id,
            BusinessCalendarCreate(name="Conflicting default", timezone="UTC"),
            actor,
        )
        with pytest.raises(BusinessCalendarConflict):
            service.transition_calendar(
                organization_id,
                conflicting.id,
                "activate",
                actor,
            )

        first = service.create_date_exception(
            organization_id,
            created.id,
            DateExceptionCreate(local_date="2026-12-25", mode="closed_all_day"),
            actor,
            idempotency_key="postgres-exception-001",
        )
        with pytest.raises(BusinessCalendarConflict):
            service.create_date_exception(
                organization_id,
                created.id,
                DateExceptionCreate(
                    local_date=first.local_date,
                    mode="open_all_day",
                ),
                actor,
                idempotency_key="postgres-exception-duplicate-001",
            )
        assert (
            session.scalar(
                select(BusinessCalendarIdempotencyReceiptModel).where(
                    BusinessCalendarIdempotencyReceiptModel.organization_id
                    == organization_id,
                    BusinessCalendarIdempotencyReceiptModel.idempotency_key
                    == "postgres-exception-duplicate-001",
                )
            )
            is None
        )
        actions = session.scalars(
            select(BusinessCalendarAuditEventModel.action).where(
                BusinessCalendarAuditEventModel.organization_id == organization_id
            )
        ).all()
        assert actions.count("date_exception.created") == 1
    engine.dispose()


def test_prd015_postgresql_lock_prevents_lost_schedule_update() -> None:
    engine = create_engine(_database_url())
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        actor, _foreign_actor, organization_id, _foreign_organization_id = _seed(
            session
        )
        calendar = _service(session).create_calendar(
            organization_id,
            BusinessCalendarCreate(name="Concurrency", timezone="UTC"),
            actor,
        )

    barrier = Barrier(2)

    def replace(start: str, end: str) -> str:
        with sessions() as session:
            barrier.wait()
            try:
                _service(session).replace_weekly_schedule(
                    organization_id,
                    calendar.id,
                    WeeklyScheduleReplace(
                        expected_version=calendar.version,
                        days=[
                            WeeklyDayInput(
                                weekday=1,
                                intervals=[LocalTimeInterval(start=start, end=end)],
                            )
                        ],
                    ),
                    actor,
                )
            except ScheduleVersionConflict:
                return "version_conflict"
            return "committed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda interval: replace(*interval),
                (("08:00", "12:00"), ("13:00", "17:00")),
            )
        )
    assert sorted(outcomes) == ["committed", "version_conflict"]
    engine.dispose()


def test_prd015_alembic_downgrade_and_reupgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTWA_DATABASE_URL", _database_url())
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    try:
        command.downgrade(configuration, "20260807_0015")
        engine = create_engine(_database_url())
        assert "business_calendar" not in inspect(engine).get_table_names()
        engine.dispose()

        command.upgrade(configuration, "20260808_0016")
        upgraded = create_engine(_database_url())
        assert "business_calendar" in inspect(upgraded).get_table_names()
        upgraded.dispose()
    finally:
        get_settings.cache_clear()
