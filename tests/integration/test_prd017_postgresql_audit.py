import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.audit.service import AuditCursorCodec, AuditQueryService
from app.domain.audit.contracts import AuditEventDraft
from app.domain.audit.errors import AuditRangeTooLarge
from app.domain.user.contracts import User
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.plan_support import allow_all_plan_enforcement

DATABASE_URL = os.getenv("BOTWA_PRD017_POSTGRES_URL") or os.getenv(
    "BOTWA_PRD016_POSTGRES_URL"
)
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD017_POSTGRES_URL is required for explicit PostgreSQL tests",
)
NOW = datetime(2026, 8, 8, 18, tzinfo=UTC)


def _url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _seed(session: Session) -> tuple[UUID, UUID, User, User]:
    organization_a, organization_b = uuid4(), uuid4()
    user_a, platform_user = uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_a,
                name="PRD017 A",
                slug=f"prd017-a-{organization_a}",
                status="active",
            ),
            OrganizationModel(
                id=organization_b,
                name="PRD017 B",
                slug=f"prd017-b-{organization_b}",
                status="active",
            ),
        )
    )
    session.flush()
    session.add_all(
        (
            UserModel(
                id=user_a,
                organization_id=organization_a,
                email=f"{user_a}@prd017.invalid",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
            UserModel(
                id=platform_user,
                organization_id=organization_b,
                email=f"{platform_user}@prd017.invalid",
                password_hash="x",
                role="platform_admin",
                status="active",
            ),
        )
    )
    session.commit()
    return (
        organization_a,
        organization_b,
        User(
            id=user_a,
            organization_id=organization_a,
            email=f"{user_a}@prd017.invalid",
            role="organization_owner",
        ),
        User(
            id=platform_user,
            organization_id=organization_b,
            email=f"{platform_user}@prd017.invalid",
            role="platform_admin",
        ),
    )


def _draft(organization_id: UUID, actor: User, index: int) -> AuditEventDraft:
    return AuditEventDraft(
        organization_id=organization_id,
        actor_type="user",
        actor_user_id=actor.id,
        actor_role=actor.role,
        action="bot.updated" if index % 2 else "bot.deactivated",
        resource_type="bot",
        resource_id=uuid4(),
        metadata={"changed_fields": ["name"]},
        correlation_id=uuid4(),
        occurred_at=NOW - timedelta(seconds=index // 3),
    )


def _query(session: Session) -> AuditQueryService:
    return AuditQueryService(
        SqlAlchemyAuditRepository(session),
        cursor_codec=AuditCursorCodec("postgres-audit-secret"),
        plan_enforcement=allow_all_plan_enforcement(),
    )


def test_prd017_postgresql_schema_atomicity_tenant_and_query() -> None:
    engine = create_engine(_url())
    assert engine.dialect.name == "postgresql"
    configuration = Config("alembic.ini")
    get_settings.cache_clear()
    command.upgrade(configuration, "20260808_0018")
    inspector = inspect(engine)
    assert "audit_event" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("audit_event")} == {
        "id",
        "organization_id",
        "actor_type",
        "actor_user_id",
        "actor_role",
        "action",
        "resource_type",
        "resource_id",
        "result",
        "metadata",
        "correlation_id",
        "occurred_at",
        "created_at",
    }
    assert {index["name"] for index in inspector.get_indexes("audit_event")} >= {
        "ix_audit_event_org_occurred_id",
        "ix_audit_event_org_action_occurred",
        "ix_audit_event_org_actor_occurred",
        "ix_audit_event_org_resource_occurred",
    }
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        organization_a, organization_b, actor_a, platform = _seed(session)
        writer = SqlAlchemyAuditRepository(session)
        for index in range(6):
            writer.append(_draft(organization_a, actor_a, index))
        writer.append(
            AuditEventDraft(
                organization_id=organization_b,
                actor_type="system",
                action="organization.created",
                resource_type="organization",
                resource_id=organization_b,
                occurred_at=NOW,
            )
        )
        session.commit()
        first = _query(session).query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(days=365),
            to=NOW + timedelta(seconds=1),
            limit=2,
        )
        assert len(first.items) == 2 and first.next_cursor is not None
        second = _query(session).query(
            organization_a,
            platform,
            from_=NOW - timedelta(days=365),
            to=NOW + timedelta(seconds=1),
            cursor=first.next_cursor,
            limit=2,
        )
        assert len(second.items) == 2
        assert all(
            item.actor.user_id == actor_a.id for item in first.items + second.items
        )
        with pytest.raises(AuditRangeTooLarge):
            _query(session).query(
                organization_a,
                actor_a,
                from_=NOW - timedelta(days=367),
                to=NOW,
            )
        count_before = session.scalar(select(func.count(AuditEventModel.id)))
        writer.append(_draft(organization_a, actor_a, 99))
        session.rollback()
        assert session.scalar(select(func.count(AuditEventModel.id))) == count_before

        invalid_org = OrganizationModel(
            id=uuid4(), name="Rollback", slug=f"rollback-{uuid4()}", status="active"
        )
        session.add(invalid_org)
        session.add(
            AuditEventModel(
                organization_id=invalid_org.id,
                actor_type="user",
                actor_user_id=uuid4(),
                actor_role="organization_owner",
                action="organization.created",
                resource_type="organization",
                resource_id=invalid_org.id,
                result="success",
                metadata_data={},
                occurred_at=NOW,
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(OrganizationModel, invalid_org.id) is None
    engine.dispose()


def test_prd017_postgresql_10000_event_queries_are_o1() -> None:
    engine = create_engine(_url())
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        organization_a, _, actor_a, _ = _seed(session)
        session.bulk_save_objects(
            [
                AuditEventModel(
                    organization_id=organization_a,
                    actor_type="user",
                    actor_user_id=actor_a.id,
                    actor_role=actor_a.role,
                    action="bot.updated" if index % 2 else "bot.deactivated",
                    resource_type="bot",
                    resource_id=uuid4(),
                    result="success",
                    metadata_data={"changed_fields": ["name"]},
                    occurred_at=NOW - timedelta(seconds=index),
                    created_at=NOW,
                )
                for index in range(10_000)
            ]
        )
        session.commit()
        selects = 0

        def count_selects(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            nonlocal selects
            if statement.lstrip().upper().startswith("SELECT"):
                selects += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        service = _query(session)
        first = service.query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(days=1),
            to=NOW + timedelta(seconds=1),
        )
        filtered = service.query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(days=1),
            to=NOW + timedelta(seconds=1),
            action="bot.updated",
        )
        resource = service.query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(days=1),
            to=NOW + timedelta(seconds=1),
            resource_type="bot",
        )
        assert first.next_cursor is not None
        service.query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(days=1),
            to=NOW + timedelta(seconds=1),
            cursor=first.next_cursor,
        )
        event.remove(engine, "before_cursor_execute", count_selects)
        assert first.items and filtered.items and resource.items
        assert selects == 4
    engine.dispose()


def test_prd017_postgresql_migration_cycle_single_head() -> None:
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "20260808_0018")
    command.downgrade(configuration, "20260808_0017")
    command.upgrade(configuration, "20260808_0018")
    engine = create_engine(_url())
    try:
        assert "audit_event" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
