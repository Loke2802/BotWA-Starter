from collections.abc import Generator
from uuid import uuid4

import pytest
from app.infrastructure.database import Base
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.operations import reset_user_password
from app.security.passwords import PasswordService
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


def _seed_user(session: Session) -> tuple[object, str, int]:
    organization_id = uuid4()
    organization = OrganizationModel(
        id=organization_id,
        name="Platform",
        slug="platform-reset",
    )
    old_hash = PasswordService().hash("old-password-123")
    user = UserModel(
        organization_id=organization_id,
        email="admin@example.com",
        password_hash=old_hash,
        role="platform_admin",
        status="active",
    )
    session.add_all((organization, user))
    session.commit()
    return user.id, old_hash, user.auth_version


def test_reset_changes_hash_invalidates_tokens_and_writes_audit(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, old_hash, original_auth_version = _seed_user(session)
    monkeypatch.setattr(reset_user_password, "SessionLocal", lambda: session)

    code, result = reset_user_password.reset(
        email=" ADMIN@example.com ",
        new_password="new-password-456",
        confirmation="new-password-456",
    )

    persisted = session.get(UserModel, user_id)
    assert code == 0
    assert result["status"] == "password_reset"
    assert persisted is not None
    assert persisted.password_hash != old_hash
    assert PasswordService().verify("new-password-456", persisted.password_hash)
    assert persisted.auth_version == original_auth_version + 1
    audit = (
        session.execute(Base.metadata.tables["audit_event"].select()).mappings().one()
    )
    assert audit["action"] == "user.password_changed"
    assert audit["actor_type"] == "system"
    assert audit["resource_id"] == user_id


@pytest.mark.parametrize(
    ("new_password", "confirmation", "expected_status"),
    (
        ("new-password-456", "different-password", "password_mismatch"),
        ("too-short", "too-short", "password_too_short"),
    ),
)
def test_invalid_password_does_not_change_user(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    new_password: str,
    confirmation: str,
    expected_status: str,
) -> None:
    user_id, old_hash, original_auth_version = _seed_user(session)
    monkeypatch.setattr(reset_user_password, "SessionLocal", lambda: session)

    code, result = reset_user_password.reset(
        email="admin@example.com",
        new_password=new_password,
        confirmation=confirmation,
    )

    persisted = session.get(UserModel, user_id)
    assert code == 2
    assert result["status"] == expected_status
    assert persisted is not None
    assert persisted.password_hash == old_hash
    assert persisted.auth_version == original_auth_version
    assert session.execute(Base.metadata.tables["audit_event"].select()).first() is None
