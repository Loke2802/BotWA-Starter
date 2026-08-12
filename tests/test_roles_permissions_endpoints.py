from collections.abc import Generator
from dataclasses import dataclass

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
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.plan_support import allow_all_plan_enforcement, no_op_plan_repository


@dataclass(frozen=True)
class Runtime:
    client: TestClient
    session: Session


@pytest.fixture
def runtime() -> Generator[Runtime]:
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
        return OrganizationService(
            repository=OrganizationRepository(session=session),
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
            yield Runtime(client=test_client, session=session)
    finally:
        session.close()
        app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_organization(client: TestClient, slug: str) -> str:
    response = client.post(
        "/organizations",
        json={"name": slug.title(), "slug": slug},
    )
    assert response.status_code == 201
    return str(response.json()["organization"]["id"])


def create_user(
    client: TestClient,
    organization_id: str,
    email: str,
    password: str = "valid-password-123",
    token: str | None = None,
    role: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "organization_id": organization_id,
        "email": email,
        "password": password,
    }
    if role is not None:
        payload["role"] = role
    headers = auth_header(token) if token is not None else None
    response = client.post("/users", json=payload, headers=headers)
    assert response.status_code == 201
    return dict(response.json()["user"])


def login(
    client: TestClient,
    email: str,
    password: str = "valid-password-123",
) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def make_platform_admin(runtime: Runtime, email: str) -> str:
    repository = UserRepository(session=runtime.session)
    model = repository.find_by_email(email)
    assert model is not None
    model.role = "platform_admin"
    runtime.session.commit()
    return login(runtime.client, email)


def test_roles_and_effective_permissions(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_organization(client, "acme")
    owner = create_user(client, organization_id, "owner@example.com")
    owner_token = login(client, "owner@example.com")

    roles = client.get("/roles", headers=auth_header(owner_token))
    permissions = client.get("/permissions/me", headers=auth_header(owner_token))

    assert owner["role"] == "organization_owner"
    assert roles.status_code == 200
    assert roles.json()["total"] == 5
    assert permissions.status_code == 200
    assert permissions.json()["role"] == "organization_owner"
    assert "roles.assign" in permissions.json()["permissions"]


def test_default_viewer_and_immediate_role_change(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_organization(client, "acme")
    create_user(client, organization_id, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    viewer = create_user(
        client,
        organization_id,
        "viewer@example.com",
        token=owner_token,
    )
    viewer_token = login(client, "viewer@example.com")

    before = client.get("/users", headers=auth_header(viewer_token))
    assign = client.patch(
        f"/users/{viewer['id']}/role",
        json={"role": "operator"},
        headers=auth_header(owner_token),
    )
    after = client.get("/users", headers=auth_header(viewer_token))

    assert viewer["role"] == "viewer"
    assert before.status_code == 403
    assert assign.status_code == 200
    assert assign.json()["user"]["role"] == "operator"
    assert after.status_code == 200


def test_role_assignment_restrictions(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_organization(client, "acme")
    owner = create_user(client, organization_id, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    admin = create_user(
        client,
        organization_id,
        "admin@example.com",
        token=owner_token,
        role="organization_admin",
    )
    operator = create_user(
        client,
        organization_id,
        "operator@example.com",
        token=owner_token,
        role="operator",
    )
    operator_token = login(client, "operator@example.com")
    admin_token = login(client, "admin@example.com")

    operator_assign = client.patch(
        f"/users/{admin['id']}/role",
        json={"role": "viewer"},
        headers=auth_header(operator_token),
    )
    admin_owner_assign = client.patch(
        f"/users/{operator['id']}/role",
        json={"role": "organization_owner"},
        headers=auth_header(admin_token),
    )
    owner_platform_assign = client.patch(
        f"/users/{operator['id']}/role",
        json={"role": "platform_admin"},
        headers=auth_header(owner_token),
    )
    self_change = client.patch(
        f"/users/{owner['id']}/role",
        json={"role": "viewer"},
        headers=auth_header(owner_token),
    )

    assert operator_assign.status_code == 403
    assert admin_owner_assign.status_code == 403
    assert owner_platform_assign.status_code == 403
    assert self_change.status_code == 403


def test_multi_tenancy_and_platform_admin(runtime: Runtime) -> None:
    client = runtime.client
    org_a = create_organization(client, "acme")
    org_b = create_organization(client, "beta")
    create_user(client, org_a, "owner-a@example.com")
    create_user(client, org_b, "owner-b@example.com")
    token_a = login(client, "owner-a@example.com")
    platform_user = create_user(
        client,
        org_a,
        "platform@example.com",
        token=token_a,
    )
    platform_token = make_platform_admin(runtime, "platform@example.com")

    blocked_org = client.patch(
        f"/organizations/{org_b}",
        json={"name": "Beta Blocked"},
        headers=auth_header(token_a),
    )
    blocked_users = client.get(
        f"/users/{platform_user['id']}",
        headers=auth_header(login(client, "owner-b@example.com")),
    )
    tenant_list = client.get("/organizations", headers=auth_header(token_a))
    platform_list = client.get("/organizations", headers=auth_header(platform_token))

    assert blocked_org.status_code == 403
    assert blocked_users.status_code == 403
    assert tenant_list.status_code == 200
    assert tenant_list.json()["total"] == 1
    assert platform_list.status_code == 200
    assert platform_list.json()["total"] == 2


def test_last_owner_degrade_and_deactivate_are_blocked(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_organization(client, "acme")
    owner = create_user(client, organization_id, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    create_user(
        client,
        organization_id,
        "platform@example.com",
        token=owner_token,
    )
    platform_token = make_platform_admin(runtime, "platform@example.com")

    degrade = client.patch(
        f"/users/{owner['id']}/role",
        json={"role": "viewer"},
        headers=auth_header(platform_token),
    )
    deactivate = client.post(
        f"/users/{owner['id']}/deactivate",
        headers=auth_header(platform_token),
    )

    assert degrade.status_code == 409
    assert deactivate.status_code == 409
