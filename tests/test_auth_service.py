from collections.abc import Generator

import pytest
from app.application.auth.service import (
    AuthInactiveUserError,
    AuthInvalidCredentialsError,
    AuthInvalidTokenError,
    AuthService,
)
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.domain.organization.contracts import OrganizationCreate
from app.domain.user.contracts import UserCreate
from app.infrastructure.database import Base
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.security.passwords import PasswordService
from app.security.tokens import AccessTokenService
from argon2 import PasswordHasher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)()
    try:
        yield test_session
    finally:
        test_session.close()


@pytest.fixture
def user_service(session: Session) -> UserService:
    password_service = PasswordService(
        hasher=PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1),
    )
    return UserService(
        repository=UserRepository(session=session),
        organization_repository=OrganizationRepository(session=session),
        password_service=password_service,
        session=session,
    )


@pytest.fixture
def auth_service(user_service: UserService) -> AuthService:
    token_service = AccessTokenService(
        secret_key="test-secret-key-with-at-least-32-bytes",
        algorithm="HS256",
        expires_minutes=30,
    )
    return AuthService(user_service=user_service, token_service=token_service)


@pytest.fixture
def organization_service(session: Session) -> OrganizationService:
    return OrganizationService(
        repository=OrganizationRepository(session=session),
        session=session,
    )


def create_user(
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="owner@example.com",
            password="valid-password-123",
        ),
    )


def test_login_returns_token_and_records_last_login(
    session: Session,
    organization_service: OrganizationService,
    user_service: UserService,
    auth_service: AuthService,
) -> None:
    create_user(organization_service, user_service)

    token = auth_service.login("owner@example.com", "valid-password-123")
    model = UserRepository(session=session).find_by_email("owner@example.com")

    assert token.token_type == "bearer"
    assert token.access_token
    assert token.expires_in == 1800
    assert model is not None
    assert model.last_login_at is not None


def test_login_rejects_wrong_password(
    organization_service: OrganizationService,
    user_service: UserService,
    auth_service: AuthService,
) -> None:
    create_user(organization_service, user_service)

    with pytest.raises(AuthInvalidCredentialsError):
        auth_service.login("owner@example.com", "wrong-password")


def test_login_rejects_inactive_user(
    organization_service: OrganizationService,
    user_service: UserService,
    auth_service: AuthService,
) -> None:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    user = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="owner@example.com",
            password="valid-password-123",
        ),
    )
    user_service.deactivate(user.id, actor=user)

    with pytest.raises(AuthInactiveUserError):
        auth_service.login("owner@example.com", "valid-password-123")


def test_token_valid_altered_expired_and_invalidated_after_password_change(
    organization_service: OrganizationService,
    user_service: UserService,
    auth_service: AuthService,
) -> None:
    create_user(organization_service, user_service)
    token = auth_service.login("owner@example.com", "valid-password-123")
    current = auth_service.authenticate_token(token.access_token)

    assert current.email == "owner@example.com"

    with pytest.raises(AuthInvalidTokenError):
        auth_service.authenticate_token(f"{token.access_token}x")

    expired_auth = AuthService(
        user_service=user_service,
        token_service=AccessTokenService(
            secret_key="test-secret-key-with-at-least-32-bytes",
            algorithm="HS256",
            expires_minutes=-1,
        ),
    )
    expired = expired_auth.login("owner@example.com", "valid-password-123")
    with pytest.raises(AuthInvalidTokenError):
        auth_service.authenticate_token(expired.access_token)

    auth_service.change_password(
        user=current,
        current_password="valid-password-123",
        new_password="new-valid-password-123",
    )
    with pytest.raises(AuthInvalidTokenError):
        auth_service.authenticate_token(token.access_token)
    with pytest.raises(AuthInvalidCredentialsError):
        auth_service.login("owner@example.com", "valid-password-123")
    assert auth_service.login("owner@example.com", "new-valid-password-123")
