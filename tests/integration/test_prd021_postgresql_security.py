import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.users.service import (
    LastOwnerProtectionError,
    UserAuthenticationRequiredError,
    UserService,
)
from app.domain.user.contracts import User, UserCreate
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.security_rate_limit import SecurityRateLimitBucketModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.security_rate_limit_repository import (
    SqlAlchemyRateLimitRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.settings import get_settings
from app.security.passwords import PasswordService
from app.security.rate_limit import RateLimitService
from argon2 import PasswordHasher
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from tests.plan_support import allow_all_plan_enforcement

DATABASE_URL = os.getenv("BOTWA_PRD021_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD021_POSTGRES_URL is required for explicit PostgreSQL tests",
)


def _url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _alembic(revision: str) -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), revision)


def _user_service(session: Session) -> UserService:
    return UserService(
        UserRepository(session),
        OrganizationRepository(session),
        PasswordService(PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)),
        session,
        SqlAlchemyAuditRepository(session),
        allow_all_plan_enforcement(),
    )


def _organization(session: Session) -> OrganizationModel:
    now = datetime.now(UTC)
    row = OrganizationModel(
        id=uuid4(),
        name="PRD-021",
        slug=f"prd021-{uuid4().hex[:12]}",
        status="active",
        settings={},
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    return row


def test_prd021_migration_cycle_single_head() -> None:
    _alembic("20260813_0021")
    _alembic("20260813_0022")
    command.downgrade(Config("alembic.ini"), "20260813_0021")
    _alembic("20260813_0022")
    engine = create_engine(_url())
    try:
        assert "security_rate_limit_bucket" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_rate_limit_is_atomic_across_postgresql_workers() -> None:
    _alembic("20260813_0022")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine)
    barrier = Barrier(10)

    def consume() -> bool:
        with factory() as session:
            barrier.wait(timeout=10)
            return (
                RateLimitService(
                    SqlAlchemyRateLimitRepository(session), hmac_key="r" * 48
                )
                .check(
                    scope="auth_login",
                    identity="owner@example.invalid|203.0.113.10",
                    limit=5,
                    window_seconds=60,
                )
                .allowed
            )

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = [
            future.result(timeout=20)
            for future in [executor.submit(consume) for _ in range(10)]
        ]

    with factory() as session:
        row = session.scalars(select(SecurityRateLimitBucketModel)).one()
        assert row.attempt_count == 10
        assert "owner" not in row.key_hash
    assert sum(results) == 5
    engine.dispose()


def test_concurrent_first_owner_bootstrap_creates_exactly_one_owner() -> None:
    _alembic("20260813_0022")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine)
    with factory() as session:
        organization_id = _organization(session).id
    barrier = Barrier(2)

    def create_owner(index: int) -> str:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                _user_service(session).create(
                    UserCreate(
                        organization_id=organization_id,
                        email=f"owner-{index}@example.invalid",
                        password="valid-password-123",
                    )
                )
                return "created"
            except UserAuthenticationRequiredError:
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [executor.submit(create_owner, index) for index in range(2)]
        ]

    with factory() as session:
        owners = session.scalars(
            select(UserModel).where(
                UserModel.organization_id == organization_id,
                UserModel.role == "organization_owner",
                UserModel.status == "active",
            )
        ).all()
    assert sorted(results) == ["created", "rejected"]
    assert len(owners) == 1
    engine.dispose()


def test_concurrent_owner_deactivation_never_leaves_zero_active_owners() -> None:
    _alembic("20260813_0022")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine)
    with factory() as session:
        organization = _organization(session)
        organization_id = organization.id
        service = _user_service(session)
        first = service.create(
            UserCreate(
                organization_id=organization_id,
                email="first@example.invalid",
                password="valid-password-123",
            )
        )
        platform = User(
            id=uuid4(),
            organization_id=organization_id,
            email="platform@example.invalid",
            role="platform_admin",
        )
        session.add(
            UserModel(
                id=platform.id,
                organization_id=organization_id,
                email=platform.email,
                password_hash="not-used",
                role=platform.role,
                status="active",
                auth_version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
        second = service.create(
            UserCreate(
                organization_id=organization.id,
                email="second@example.invalid",
                password="valid-password-123",
                role="organization_owner",
            ),
            actor=platform,
        )
    barrier = Barrier(2)

    def deactivate(user_id: UUID) -> str:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                _user_service(session).deactivate(user_id, platform)
                return "deactivated"
            except LastOwnerProtectionError:
                return "protected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in (
                executor.submit(deactivate, first.id),
                executor.submit(deactivate, second.id),
            )
        ]
    with factory() as session:
        active_owners = session.scalars(
            select(UserModel).where(
                UserModel.organization_id == organization_id,
                UserModel.role == "organization_owner",
                UserModel.status == "active",
            )
        ).all()
    assert sorted(results) == ["deactivated", "protected"]
    assert len(active_owners) == 1
    engine.dispose()
