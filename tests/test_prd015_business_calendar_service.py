from collections.abc import Generator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from app.application.business_calendar.service import BusinessCalendarService
from app.domain.business_calendar.contracts import (
    BusinessCalendarCreate,
    BusinessCalendarUpdate,
    DateExceptionCreate,
    HolidayCreate,
    LocalTimeInterval,
    ManualOverrideCreate,
    ManualOverrideRevoke,
    WeeklyDayInput,
    WeeklyScheduleReplace,
)
from app.domain.business_calendar.errors import (
    BusinessCalendarConflict,
    BusinessCalendarNotFound,
    BusinessCalendarPersistenceError,
    IdempotencyConflict,
    ScheduleVersionConflict,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_calendar import (
    BusinessCalendarAuditEventModel,
    BusinessCalendarIdempotencyReceiptModel,
    BusinessCalendarModel,
    BusinessCalendarWeeklyIntervalModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
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
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _actor(organization_id: UUID, role: str = "organization_owner") -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"{uuid4()}@example.com",
        role=role,
    )


def _setup(
    session: Session,
) -> tuple[BusinessCalendarService, User, UUID, UUID]:
    organization_id, bot_id = uuid4(), uuid4()
    actor = _actor(organization_id)
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Kalivur",
                slug=str(organization_id)[:12],
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
                id=actor.id,
                organization_id=organization_id,
                email=actor.email,
                password_hash="x",
                role=actor.role,
                status="active",
            ),
        )
    )
    session.commit()
    return (
        BusinessCalendarService(
            BusinessCalendarRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
        ),
        actor,
        organization_id,
        bot_id,
    )


def _create(
    service: BusinessCalendarService,
    actor: User,
    organization_id: UUID,
    *,
    key: str = "calendar-create-001",
) -> UUID:
    return service.create_calendar(
        organization_id,
        BusinessCalendarCreate(name="Support", timezone="UTC"),
        actor,
        idempotency_key=key,
    ).id


def _weekly(expected_version: int) -> WeeklyScheduleReplace:
    return WeeklyScheduleReplace(
        expected_version=expected_version,
        days=[
            WeeklyDayInput(
                weekday=1,
                intervals=[
                    LocalTimeInterval(start="09:00", end="12:00"),
                    LocalTimeInterval(start="13:00", end="17:00"),
                ],
            )
        ],
    )


def test_calendar_creation_is_idempotent_audited_and_tenant_scoped(
    session: Session,
) -> None:
    service, actor, organization_id, bot_id = _setup(session)
    payload = BusinessCalendarCreate(
        name="Support",
        bot_id=bot_id,
        timezone="America/Lima",
    )
    first = service.create_calendar(
        organization_id, payload, actor, idempotency_key="calendar-create-001"
    )
    replay = service.create_calendar(
        organization_id, payload, actor, idempotency_key="calendar-create-001"
    )

    assert replay == first
    assert len(session.scalars(select(BusinessCalendarModel)).all()) == 1
    assert (
        len(session.scalars(select(BusinessCalendarIdempotencyReceiptModel)).all()) == 1
    )
    audits = session.scalars(select(BusinessCalendarAuditEventModel)).all()
    assert len(audits) == 1
    assert audits[0].action == "calendar.created"
    assert set(audits[0].changes) == {"timezone", "bot_id"}

    with pytest.raises(IdempotencyConflict):
        service.create_calendar(
            organization_id,
            BusinessCalendarCreate(name="Another", timezone="UTC"),
            actor,
            idempotency_key="calendar-create-001",
        )

    foreign_org = uuid4()
    foreign_actor = _actor(foreign_org)
    with pytest.raises(BusinessCalendarNotFound):
        service.get_calendar(foreign_org, first.id, foreign_actor)


def test_versioning_schedule_and_archived_calendar_are_fail_safe(
    session: Session,
) -> None:
    service, actor, organization_id, _bot_id = _setup(session)
    calendar_id = _create(service, actor, organization_id)
    schedule = service.replace_weekly_schedule(
        organization_id,
        calendar_id,
        _weekly(1),
        actor,
        idempotency_key="weekly-replace-001",
    )
    assert schedule.calendar_version == 2
    assert len(schedule.days[0].intervals) == 2
    assert (
        service.replace_weekly_schedule(
            organization_id,
            calendar_id,
            _weekly(1),
            actor,
            idempotency_key="weekly-replace-001",
        )
        == schedule
    )

    with pytest.raises(ScheduleVersionConflict):
        service.update_calendar(
            organization_id,
            calendar_id,
            BusinessCalendarUpdate(expected_version=1, name="Stale"),
            actor,
        )

    archived = service.transition_calendar(
        organization_id, calendar_id, "archive", actor
    )
    assert archived.status == "archived"
    with pytest.raises(BusinessCalendarConflict):
        service.replace_weekly_schedule(
            organization_id,
            calendar_id,
            _weekly(archived.version),
            actor,
        )


def test_resolution_uses_override_exception_holiday_and_weekly_layers(
    session: Session,
) -> None:
    service, actor, organization_id, _bot_id = _setup(session)
    calendar_id = _create(service, actor, organization_id)
    schedule = service.replace_weekly_schedule(
        organization_id, calendar_id, _weekly(1), actor
    )
    holiday = service.create_holiday(
        organization_id,
        calendar_id,
        HolidayCreate(
            local_date=date(2026, 8, 10),
            name="Closure",
            scope="full_day",
        ),
        actor,
    )
    assert holiday.scope == "full_day"
    exception = service.create_date_exception(
        organization_id,
        calendar_id,
        DateExceptionCreate(
            local_date=date(2026, 8, 10),
            mode="open_all_day",
        ),
        actor,
    )
    assert exception.mode == "open_all_day"
    override = service.create_override(
        organization_id,
        calendar_id,
        ManualOverrideCreate(
            decision="closed",
            starts_at=datetime(2026, 8, 10, 10, tzinfo=UTC),
            ends_at=datetime(2026, 8, 10, 11, tzinfo=UTC),
            reason="Emergency closure",
        ),
        actor,
    )
    activated = service.transition_calendar(
        organization_id, calendar_id, "activate", actor
    )
    assert activated.version == schedule.calendar_version + 4

    closed = service.resolve(
        organization_id,
        calendar_id,
        datetime(2026, 8, 10, 10, 30, tzinfo=UTC),
        actor,
    )
    assert (closed.state, closed.winning_rule_type) == (
        "closed",
        "manual_override",
    )

    service.revoke_override(
        organization_id,
        calendar_id,
        override.id,
        ManualOverrideRevoke(expected_version=override.version),
        actor,
    )
    reopened = service.resolve(
        organization_id,
        calendar_id,
        datetime(2026, 8, 10, 10, 30, tzinfo=UTC),
        actor,
    )
    assert (reopened.state, reopened.winning_rule_type) == (
        "open",
        "date_exception",
    )


def test_failed_schedule_commit_rolls_back_intervals_audit_and_version(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, actor, organization_id, _bot_id = _setup(session)
    calendar_id = _create(service, actor, organization_id)
    first = service.replace_weekly_schedule(
        organization_id, calendar_id, _weekly(1), actor
    )
    original_audit_count = len(
        session.scalars(select(BusinessCalendarAuditEventModel)).all()
    )
    real_rollback = session.rollback
    rollback_calls = 0

    def fail_commit() -> None:
        raise SQLAlchemyError("forced commit failure")

    def track_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        real_rollback()

    monkeypatch.setattr(session, "commit", fail_commit)
    monkeypatch.setattr(session, "rollback", track_rollback)
    replacement = WeeklyScheduleReplace(
        expected_version=first.calendar_version,
        days=[
            WeeklyDayInput(
                weekday=1,
                intervals=[LocalTimeInterval(start="08:00", end="10:00")],
            )
        ],
    )

    with pytest.raises(BusinessCalendarPersistenceError):
        service.replace_weekly_schedule(
            organization_id,
            calendar_id,
            replacement,
            actor,
            idempotency_key="rollback-weekly-001",
        )

    assert rollback_calls == 1
    calendar = service.repository.calendar(organization_id, calendar_id)
    assert calendar is not None
    assert calendar.version == first.calendar_version
    rows = session.scalars(select(BusinessCalendarWeeklyIntervalModel)).all()
    assert [(row.start_minute, row.end_minute) for row in rows] == [
        (540, 720),
        (780, 1020),
    ]
    assert (
        len(session.scalars(select(BusinessCalendarAuditEventModel)).all())
        == original_audit_count
    )
    assert (
        session.scalar(
            select(BusinessCalendarIdempotencyReceiptModel).where(
                BusinessCalendarIdempotencyReceiptModel.idempotency_key
                == "rollback-weekly-001"
            )
        )
        is None
    )


def test_integrity_conflict_is_safe_and_rolls_back_calendar_version(
    session: Session,
) -> None:
    service, actor, organization_id, _bot_id = _setup(session)
    calendar_id = _create(service, actor, organization_id)
    first = service.create_date_exception(
        organization_id,
        calendar_id,
        DateExceptionCreate(
            local_date=date(2026, 12, 25),
            mode="closed_all_day",
        ),
        actor,
        idempotency_key="exception-first-001",
    )
    audit_count = len(session.scalars(select(BusinessCalendarAuditEventModel)).all())
    calendar = service.repository.calendar(organization_id, calendar_id)
    assert calendar is not None
    version = calendar.version

    with pytest.raises(BusinessCalendarConflict) as error:
        service.create_date_exception(
            organization_id,
            calendar_id,
            DateExceptionCreate(
                local_date=first.local_date,
                mode="open_all_day",
            ),
            actor,
            idempotency_key="exception-second-001",
        )

    assert "UNIQUE" not in str(error.value).upper()
    persisted = service.repository.calendar(organization_id, calendar_id)
    assert persisted is not None
    assert persisted.version == version
    assert (
        len(session.scalars(select(BusinessCalendarAuditEventModel)).all())
        == audit_count
    )
    assert (
        session.scalar(
            select(BusinessCalendarIdempotencyReceiptModel).where(
                BusinessCalendarIdempotencyReceiptModel.idempotency_key
                == "exception-second-001"
            )
        )
        is None
    )
