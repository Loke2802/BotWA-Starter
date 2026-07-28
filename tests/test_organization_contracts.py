from uuid import uuid4

import pytest
from app.domain.organization.contracts import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
)
from pydantic import ValidationError


def test_create_normalizes_slug() -> None:
    request = OrganizationCreate(name="Acme Inc", slug=" Acme_Inc ")

    assert request.slug == "acme-inc"


def test_create_rejects_invalid_slug() -> None:
    with pytest.raises(ValidationError):
        OrganizationCreate(name="Acme Inc", slug="Acme!")


def test_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        OrganizationCreate(name="   ", slug="acme")


def test_update_normalizes_slug() -> None:
    request = OrganizationUpdate(slug="New Slug")

    assert request.slug == "new-slug"


def test_organization_keeps_inactive_status() -> None:
    organization = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status="inactive",
    )

    assert organization.status == "inactive"
