from collections.abc import Generator
from uuid import uuid4

import pytest
from app.api.dependencies import get_organization_service
from app.application.organizations.service import OrganizationService
from app.infrastructure.database import Base
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    def override_service() -> OrganizationService:
        repository = OrganizationRepository(session=session)
        return OrganizationService(repository=repository, session=session)

    app = create_app()
    app.dependency_overrides[get_organization_service] = override_service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        session.close()
        app.dependency_overrides.clear()


def test_create_organization_endpoint(client: TestClient) -> None:
    response = client.post(
        "/organizations",
        json={"name": "Acme Inc", "slug": "Acme Inc"},
    )

    assert response.status_code == 201
    data = response.json()["organization"]
    assert data["name"] == "Acme Inc"
    assert data["slug"] == "acme-inc"
    assert data["status"] == "active"


def test_create_duplicate_slug_endpoint(client: TestClient) -> None:
    payload = {"name": "Acme", "slug": "acme"}
    assert client.post("/organizations", json=payload).status_code == 201

    response = client.post(
        "/organizations",
        json={"name": "Other", "slug": "acme"},
    )

    assert response.status_code == 409


def test_create_invalid_payload_endpoint(client: TestClient) -> None:
    response = client.post(
        "/organizations",
        json={"name": "   ", "slug": "Invalid!"},
    )

    assert response.status_code == 422


def test_get_list_update_deactivate_endpoints(client: TestClient) -> None:
    created = client.post(
        "/organizations",
        json={"name": "Acme", "slug": "acme"},
    ).json()["organization"]
    organization_id = created["id"]

    get_response = client.get(f"/organizations/{organization_id}")
    list_response = client.get("/organizations")
    update_response = client.patch(
        f"/organizations/{organization_id}",
        json={"name": "Acme Updated", "slug": "acme-updated"},
    )
    deactivate_response = client.post(
        f"/organizations/{organization_id}/deactivate",
    )
    second_deactivate_response = client.post(
        f"/organizations/{organization_id}/deactivate",
    )

    assert get_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert update_response.status_code == 200
    assert update_response.json()["organization"]["slug"] == "acme-updated"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["organization"]["status"] == "inactive"
    assert second_deactivate_response.status_code == 200
    assert second_deactivate_response.json()["organization"]["status"] == "inactive"


def test_get_missing_organization_endpoint(client: TestClient) -> None:
    response = client.get(f"/organizations/{uuid4()}")

    assert response.status_code == 404


def test_update_duplicate_slug_endpoint(client: TestClient) -> None:
    first = client.post(
        "/organizations",
        json={"name": "Acme", "slug": "acme"},
    ).json()["organization"]
    client.post("/organizations", json={"name": "Beta", "slug": "beta"})

    response = client.patch(
        f"/organizations/{first['id']}",
        json={"slug": "beta"},
    )

    assert response.status_code == 409
