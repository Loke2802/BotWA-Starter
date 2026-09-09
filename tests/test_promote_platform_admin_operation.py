from collections.abc import Generator
from uuid import uuid4

import pytest
from app.infrastructure.database import Base
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.operations import promote_platform_admin
from sqlalchemy import create_engine
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
    database_session = sessionmaker(bind=engine)()
    try:
        yield database_session
    finally:
        database_session.close()


def _seed_user(session: Session) -> UserModel:
    organization_id = uuid4()
    organization = OrganizationModel(
        id=organization_id,
        name="Platform",
        slug="platform",
    )
    user = UserModel(
        organization_id=organization_id,
        email="admin@example.com",
        password_hash="unused",
        role="organization_owner",
        status="active",
    )
    session.add_all((organization, user))
    session.commit()
    return user


def test_dry_run_does_not_change_role(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _seed_user(session)
    user_id = user.id
    monkeypatch.setattr(promote_platform_admin, "SessionLocal", lambda: session)

    code, result = promote_platform_admin.promote(
        email=" ADMIN@example.com ", apply=False
    )

    persisted = session.get(UserModel, user_id)
    assert code == 0
    assert result["status"] == "would_promote"
    assert persisted is not None
    assert persisted.role == "organization_owner"


def test_apply_promotes_invalidates_tokens_and_writes_audit(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _seed_user(session)
    user_id = user.id
    original_auth_version = user.auth_version
    monkeypatch.setattr(promote_platform_admin, "SessionLocal", lambda: session)

    code, result = promote_platform_admin.promote(email="admin@example.com", apply=True)

    persisted = session.get(UserModel, user_id)
    assert code == 0
    assert result["status"] == "promoted"
    assert persisted is not None
    assert persisted.role == "platform_admin"
    assert persisted.auth_version == original_auth_version + 1
    audit = (
        session.execute(Base.metadata.tables["audit_event"].select()).mappings().one()
    )
    assert audit["action"] == "user.role_changed"
    assert audit["actor_type"] == "system"
    assert audit["resource_id"] == user_id
