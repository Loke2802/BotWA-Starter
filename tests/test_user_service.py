from collections.abc import Generator
from uuid import UUID

import pytest
from app.application.organizations.service import OrganizationService
from app.application.users.service import (
    OrganizationInactiveError,
    UserAuthenticationRequiredError,
    UserConflictError,
    UserForbiddenError,
    UserService,
)
from app.domain.organization.contracts import OrganizationCreate
from app.domain.user.contracts import UserCreate, UserUpdate
from app.infrastructure.database import Base
from app.infrastructure.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.security.passwords import PasswordService
from argon2 import PasswordHasher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tests.plan_support import allow_all_plan_enforcement, no_op_plan_repository


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
def password_service() -> PasswordService:
    hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    return PasswordService(hasher=hasher)


@pytest.fixture
def organization_service(session: Session) -> OrganizationService:
    repository = OrganizationRepository(session=session)
    return OrganizationService(
        repository=repository,
        session=session,
        audit_writer=SqlAlchemyAuditRepository(session),
        plan_repository=no_op_plan_repository(),
    )


@pytest.fixture
def user_service(
    session: Session,
    password_service: PasswordService,
) -> UserService:
    return UserService(
        repository=UserRepository(session=session),
        organization_repository=OrganizationRepository(session=session),
        password_service=password_service,
        session=session,
        audit_writer=SqlAlchemyAuditRepository(session),
        plan_enforcement=allow_all_plan_enforcement(),
    )


def create_organization(organization_service: OrganizationService) -> UUID:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme"),
    )
    return organization.id


def test_create_user_hashes_password_and_hides_hash(
    session: Session,
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    organization_id = create_organization(organization_service)

    user = user_service.create(
        UserCreate(
            organization_id=organization_id,
            email=" Owner@Example.COM ",
            password="valid-password-123",
            first_name="Owner",
        ),
    )
    model = UserRepository(session=session).find_by_email("owner@example.com")

    assert user.email == "owner@example.com"
    assert user.first_name == "Owner"
    assert user.role == "organization_owner"
    assert model is not None
    assert model.password_hash != "valid-password-123"
    assert not hasattr(user, "password_hash")


def test_create_rejects_duplicate_email_globally(
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    first_org = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    second_org = organization_service.create(
        OrganizationCreate(name="Beta", slug="beta")
    )
    user_service.create(
        UserCreate(
            organization_id=first_org.id,
            email="owner@example.com",
            password="valid-password-123",
        ),
    )

    with pytest.raises(UserConflictError):
        user_service.create(
            UserCreate(
                organization_id=second_org.id,
                email="owner@example.com",
                password="valid-password-123",
            ),
        )


def test_create_rejects_inactive_organization(
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    owner = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="owner@example.com",
            password="valid-password-123",
        )
    )
    organization_service.deactivate(organization.id, owner)

    with pytest.raises(OrganizationInactiveError):
        user_service.create(
            UserCreate(
                organization_id=organization.id,
                email="second@example.com",
                password="valid-password-123",
            ),
        )


def test_bootstrap_allows_first_user_then_requires_authenticated_actor(
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    owner = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="owner@example.com",
            password="valid-password-123",
        ),
    )

    with pytest.raises(UserAuthenticationRequiredError):
        user_service.create(
            UserCreate(
                organization_id=organization.id,
                email="agent@example.com",
                password="valid-password-123",
            ),
        )

    created = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="agent@example.com",
            password="valid-password-123",
        ),
        actor=owner,
    )

    assert created.email == "agent@example.com"
    assert created.role == "viewer"


def test_update_rejects_organization_id_change(
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    owner = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="owner@example.com",
            password="valid-password-123",
        ),
    )

    with pytest.raises(UserForbiddenError):
        user_service.update(
            owner.id,
            UserUpdate(organization_id=organization.id),
            actor=owner,
        )


def test_update_profile_and_deactivate_are_scoped_and_idempotent(
    organization_service: OrganizationService,
    user_service: UserService,
) -> None:
    organization = organization_service.create(
        OrganizationCreate(name="Acme", slug="acme")
    )
    owner = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="owner@example.com",
            password="valid-password-123",
            first_name="Old",
        ),
    )
    agent = user_service.create(
        UserCreate(
            organization_id=organization.id,
            email="agent@example.com",
            password="valid-password-123",
        ),
        actor=owner,
    )

    updated = user_service.update(
        owner.id,
        UserUpdate(first_name="New"),
        actor=owner,
    )
    first = user_service.deactivate(agent.id, actor=owner)
    second = user_service.deactivate(agent.id, actor=owner)

    assert updated.first_name == "New"
    assert first.status == "inactive"
    assert first.deactivated_at is not None
    assert second.deactivated_at == first.deactivated_at
