from collections.abc import Generator
from uuid import uuid4

import pytest
from app.application.organizations.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationService,
)
from app.domain.organization.contracts import OrganizationCreate, OrganizationUpdate
from app.infrastructure.database import Base
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
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
def service(session: Session) -> OrganizationService:
    repository = OrganizationRepository(session=session)
    return OrganizationService(repository=repository, session=session)


def test_create_organization(service: OrganizationService) -> None:
    organization = service.create(
        OrganizationCreate(name="Acme Inc", slug="acme-inc"),
    )

    assert organization.name == "Acme Inc"
    assert organization.slug == "acme-inc"
    assert organization.status == "active"


def test_create_rejects_duplicate_slug(service: OrganizationService) -> None:
    service.create(OrganizationCreate(name="Acme", slug="acme"))

    with pytest.raises(OrganizationConflictError):
        service.create(OrganizationCreate(name="Other", slug="acme"))


def test_get_by_id(service: OrganizationService) -> None:
    created = service.create(OrganizationCreate(name="Acme", slug="acme"))

    retrieved = service.get(created.id)

    assert retrieved.id == created.id
    assert retrieved.slug == "acme"


def test_get_not_found(service: OrganizationService) -> None:
    with pytest.raises(OrganizationNotFoundError):
        service.get(uuid4())


def test_list_organizations(service: OrganizationService) -> None:
    service.create(OrganizationCreate(name="Acme", slug="acme"))
    service.create(OrganizationCreate(name="Beta", slug="beta"))

    organizations = service.list()

    assert [org.slug for org in organizations] == ["acme", "beta"]


def test_update_organization(service: OrganizationService) -> None:
    created = service.create(OrganizationCreate(name="Acme", slug="acme"))

    updated = service.update(
        created.id,
        OrganizationUpdate(name="Acme Updated", slug="acme-updated"),
    )

    assert updated.name == "Acme Updated"
    assert updated.slug == "acme-updated"


def test_update_rejects_duplicate_slug(service: OrganizationService) -> None:
    first = service.create(OrganizationCreate(name="Acme", slug="acme"))
    service.create(OrganizationCreate(name="Beta", slug="beta"))

    with pytest.raises(OrganizationConflictError):
        service.update(first.id, OrganizationUpdate(slug="beta"))


def test_deactivate_is_idempotent(service: OrganizationService) -> None:
    created = service.create(OrganizationCreate(name="Acme", slug="acme"))

    first = service.deactivate(created.id)
    second = service.deactivate(created.id)

    assert first.status == "inactive"
    assert first.deactivated_at is not None
    assert second.status == "inactive"
    assert second.deactivated_at == first.deactivated_at


def test_inactive_organization_remains_readable_and_updatable(
    service: OrganizationService,
) -> None:
    created = service.create(OrganizationCreate(name="Acme", slug="acme"))
    inactive = service.deactivate(created.id)

    retrieved = service.get(created.id)
    updated = service.update(created.id, OrganizationUpdate(name="Acme Legal"))

    assert inactive.status == "inactive"
    assert retrieved.status == "inactive"
    assert updated.name == "Acme Legal"
    assert updated.status == "inactive"
