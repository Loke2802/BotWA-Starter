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

    def override_organization_service() -> OrganizationService:
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
    app.dependency_overrides[get_organization_service] = override_organization_service
    app.dependency_overrides[get_user_service] = override_user_service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        session.close()
        app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_organization(client: TestClient, slug: str = "acme") -> str:
    response = client.post(
        "/organizations",
        json={"name": slug.title(), "slug": slug},
    )
    assert response.status_code == 201
    return str(response.json()["organization"]["id"])


def create_bootstrap_user(
    client: TestClient, organization_id: str
) -> dict[str, object]:
    response = client.post(
        "/users",
        json={
            "organization_id": organization_id,
            "email": " Owner@Example.COM ",
            "password": "valid-password-123",
            "first_name": "Owner",
        },
    )
    assert response.status_code == 201
    return dict(response.json()["user"])


def login(client: TestClient, password: str = "valid-password-123") -> str:
    response = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_create_user_endpoint_bootstrap_and_hides_password_hash(
    client: TestClient,
) -> None:
    organization_id = create_organization(client)

    user = create_bootstrap_user(client, organization_id)

    assert user["email"] == "owner@example.com"
    assert user["role"] == "organization_owner"
    assert user["status"] == "active"
    assert "password_hash" not in user


def test_create_user_endpoint_rejects_invalid_cases(client: TestClient) -> None:
    organization_id = create_organization(client)
    create_bootstrap_user(client, organization_id)

    duplicate = client.post(
        "/users",
        json={
            "organization_id": organization_id,
            "email": "owner@example.com",
            "password": "valid-password-123",
        },
        headers=auth_header(login(client)),
    )
    weak = client.post(
        "/users",
        json={
            "organization_id": organization_id,
            "email": "agent@example.com",
            "password": "short",
        },
    )
    missing_org = client.post(
        "/users",
        json={
            "organization_id": str(uuid4()),
            "email": "agent@example.com",
            "password": "valid-password-123",
        },
    )

    assert duplicate.status_code == 409
    assert weak.status_code == 422
    assert missing_org.status_code == 404


def test_create_user_endpoint_rejects_inactive_organization(
    client: TestClient,
) -> None:
    organization_id = create_organization(client)
    create_bootstrap_user(client, organization_id)
    token = login(client)
    client.post(
        f"/organizations/{organization_id}/deactivate",
        headers=auth_header(token),
    )

    response = client.post(
        "/users",
        json={
            "organization_id": organization_id,
            "email": "owner@example.com",
            "password": "valid-password-123",
        },
    )

    assert response.status_code == 409


def test_login_me_list_update_change_password_and_deactivate(
    client: TestClient,
) -> None:
    organization_id = create_organization(client)
    user = create_bootstrap_user(client, organization_id)
    token = login(client)

    me = client.get("/auth/me", headers=auth_header(token))
    agent = client.post(
        "/users",
        json={
            "organization_id": organization_id,
            "email": "agent@example.com",
            "password": "agent-password-123",
        },
        headers=auth_header(token),
    )
    listed = client.get("/users", headers=auth_header(token))
    updated = client.patch(
        f"/users/{user['id']}",
        json={"first_name": "New", "organization_id": organization_id},
        headers=auth_header(token),
    )
    profile_updated = client.patch(
        f"/users/{user['id']}",
        json={"first_name": "New"},
        headers=auth_header(token),
    )
    change = client.post(
        "/auth/change-password",
        json={
            "current_password": "valid-password-123",
            "new_password": "new-valid-password-123",
        },
        headers=auth_header(token),
    )
    old_me = client.get("/auth/me", headers=auth_header(token))
    old_login = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "valid-password-123"},
    )
    new_token = login(client, password="new-valid-password-123")
    deactivated = client.post(
        f"/users/{agent.json()['user']['id']}/deactivate",
        headers=auth_header(new_token),
    )
    second_deactivated = client.post(
        f"/users/{agent.json()['user']['id']}/deactivate",
        headers=auth_header(new_token),
    )
    inactive_agent_login = client.post(
        "/auth/login",
        json={"email": "agent@example.com", "password": "agent-password-123"},
    )

    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@example.com"
    assert agent.status_code == 201
    assert agent.json()["user"]["role"] == "viewer"
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert updated.status_code == 403
    assert profile_updated.status_code == 200
    assert profile_updated.json()["user"]["first_name"] == "New"
    assert change.status_code == 200
    assert old_me.status_code == 401
    assert old_login.status_code == 401
    assert deactivated.status_code == 200
    assert deactivated.json()["user"]["status"] == "inactive"
    assert second_deactivated.status_code == 200
    assert inactive_agent_login.status_code == 403


def test_invalid_and_tampered_tokens_return_401(client: TestClient) -> None:
    organization_id = create_organization(client)
    create_bootstrap_user(client, organization_id)
    token = login(client)

    missing = client.get("/auth/me")
    altered = client.get("/auth/me", headers=auth_header(f"{token}x"))

    assert missing.status_code == 401
    assert altered.status_code == 401


def test_prd001_organization_regression(client: TestClient) -> None:
    organization_id = create_organization(client)
    create_bootstrap_user(client, organization_id)
    token = login(client)

    response = client.patch(
        f"/organizations/{organization_id}",
        json={"name": "Acme Legal", "slug": "acme-legal"},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["organization"]["slug"] == "acme-legal"
