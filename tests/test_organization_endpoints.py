from collections.abc import Generator
from uuid import uuid4

import pytest
from app.api.dependencies import get_organization_service, get_user_service
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.infrastructure.database import Base
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.main import create_app
from app.security.passwords import PasswordService
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.plan_support import allow_all_plan_enforcement, no_op_plan_repository


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    password_service = PasswordService(
        hasher=PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1),
    )

    def override_service() -> OrganizationService:
        repository = OrganizationRepository(session=session)
        return OrganizationService(
            repository=repository,
            session=session,
            audit_writer=SqlAlchemyAuditRepository(session),
            plan_repository=no_op_plan_repository(),
        )

    def override_user_service() -> UserService:
        return UserService(
            repository=UserRepository(session=session),
            organization_repository=OrganizationRepository(session=session),
            password_service=password_service,
            session=session,
            audit_writer=SqlAlchemyAuditRepository(session),
            plan_enforcement=allow_all_plan_enforcement(),
        )

    app = create_app()
    app.dependency_overrides[get_organization_service] = override_service
    app.dependency_overrides[get_user_service] = override_user_service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        session.close()
        app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_owner_token(client: TestClient, organization_id: str) -> str:
    response = client.post(
        "/users",
        json={
            "organization_id": organization_id,
            "email": f"owner-{organization_id}@example.com",
            "password": "valid-password-123",
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "organization_owner"
    login_response = client.post(
        "/auth/login",
        json={
            "email": f"owner-{organization_id}@example.com",
            "password": "valid-password-123",
        },
    )
    assert login_response.status_code == 200
    return str(login_response.json()["access_token"])


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
    token = create_owner_token(client, organization_id)
    headers = auth_header(token)

    get_response = client.get(f"/organizations/{organization_id}", headers=headers)
    list_response = client.get("/organizations", headers=headers)
    update_response = client.patch(
        f"/organizations/{organization_id}",
        json={"name": "Acme Updated", "slug": "acme-updated"},
        headers=headers,
    )
    deactivate_response = client.post(
        f"/organizations/{organization_id}/deactivate",
        headers=headers,
    )
    second_deactivate_response = client.post(
        f"/organizations/{organization_id}/deactivate",
        headers=headers,
    )

    assert get_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert update_response.status_code == 200
    assert update_response.json()["organization"]["slug"] == "acme-updated"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["organization"]["status"] == "inactive"
    assert second_deactivate_response.status_code == 403
    assert second_deactivate_response.json()["detail"] == "account is unavailable"


def test_get_missing_organization_endpoint(client: TestClient) -> None:
    created = client.post(
        "/organizations",
        json={"name": "Acme", "slug": "acme"},
    ).json()["organization"]
    token = create_owner_token(client, created["id"])

    response = client.get(f"/organizations/{uuid4()}", headers=auth_header(token))

    assert response.status_code == 404


def test_update_duplicate_slug_endpoint(client: TestClient) -> None:
    first = client.post(
        "/organizations",
        json={"name": "Acme", "slug": "acme"},
    ).json()["organization"]
    token = create_owner_token(client, first["id"])
    client.post("/organizations", json={"name": "Beta", "slug": "beta"})

    response = client.patch(
        f"/organizations/{first['id']}",
        json={"slug": "beta"},
        headers=auth_header(token),
    )

    assert response.status_code == 409
