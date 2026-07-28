from collections.abc import Generator
from dataclasses import dataclass

import pytest
from app.api.dependencies import (
    get_bot_service,
    get_organization_service,
    get_user_service,
)
from app.application.bots.service import BotService
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.infrastructure.database import Base
from app.infrastructure.repositories.bot_repository import BotRepository
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
        )

    def override_user_service() -> UserService:
        return UserService(
            repository=UserRepository(session=session),
            organization_repository=OrganizationRepository(session=session),
            password_service=password_service,
            session=session,
        )

    def override_bot_service() -> BotService:
        return BotService(
            repository=BotRepository(session=session),
            organization_repository=OrganizationRepository(session=session),
            session=session,
        )

    app = create_app()
    app.dependency_overrides[get_organization_service] = override_organization_service
    app.dependency_overrides[get_user_service] = override_user_service
    app.dependency_overrides[get_bot_service] = override_bot_service
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
    token: str | None = None,
    role: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "organization_id": organization_id,
        "email": email,
        "password": "valid-password-123",
    }
    if role is not None:
        payload["role"] = role
    headers = auth_header(token) if token is not None else None
    response = client.post("/users", json=payload, headers=headers)
    assert response.status_code == 201
    return dict(response.json()["user"])


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "valid-password-123"},
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


def create_bot(
    client: TestClient,
    token: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Support Bot",
        "slug": "Support Bot",
        "default_language": "es",
        "timezone": "America/Lima",
    }
    if payload is not None:
        body.update(payload)
    response = client.post("/bots", json=body, headers=auth_header(token))
    assert response.status_code == 201
    return dict(response.json()["bot"])


def test_create_get_list_update_activate_deactivate_bot(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_organization(client, "acme")
    create_user(client, organization_id, "owner@example.com")
    token = login(client, "owner@example.com")

    bot = create_bot(client, token)
    fetched = client.get(f"/bots/{bot['id']}", headers=auth_header(token))
    listed = client.get("/bots", headers=auth_header(token))
    updated = client.patch(
        f"/bots/{bot['id']}",
        json={
            "name": "Updated Bot",
            "slug": "updated_bot",
            "welcome_message": "Hola",
            "timezone": "America/Bogota",
        },
        headers=auth_header(token),
    )
    activated = client.post(f"/bots/{bot['id']}/activate", headers=auth_header(token))
    second_activated = client.post(
        f"/bots/{bot['id']}/activate",
        headers=auth_header(token),
    )
    deactivated = client.post(
        f"/bots/{bot['id']}/deactivate",
        headers=auth_header(token),
    )
    second_deactivated = client.post(
        f"/bots/{bot['id']}/deactivate",
        headers=auth_header(token),
    )

    assert bot["organization_id"] == organization_id
    assert bot["slug"] == "support-bot"
    assert bot["status"] == "inactive"
    assert fetched.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert updated.status_code == 200
    assert updated.json()["bot"]["slug"] == "updated-bot"
    assert activated.status_code == 200
    assert activated.json()["bot"]["status"] == "active"
    assert second_activated.status_code == 200
    assert deactivated.status_code == 200
    assert deactivated.json()["bot"]["status"] == "inactive"
    assert second_deactivated.status_code == 200


def test_slug_unique_per_organization(runtime: Runtime) -> None:
    client = runtime.client
    org_a = create_organization(client, "acme")
    org_b = create_organization(client, "beta")
    create_user(client, org_a, "owner-a@example.com")
    create_user(client, org_b, "owner-b@example.com")
    token_a = login(client, "owner-a@example.com")
    token_b = login(client, "owner-b@example.com")
    create_bot(client, token_a, {"slug": "shared"})

    duplicate = client.post(
        "/bots",
        json={"name": "Other", "slug": "shared"},
        headers=auth_header(token_a),
    )
    same_slug_other_org = client.post(
        "/bots",
        json={"name": "Other", "slug": "shared"},
        headers=auth_header(token_b),
    )

    assert duplicate.status_code == 409
    assert same_slug_other_org.status_code == 201


def test_missing_and_inactive_organization(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    client.post(f"/organizations/{org}/deactivate", headers=auth_header(token))

    create_response = client.post(
        "/bots",
        json={"organization_id": org, "name": "Bot", "slug": "bot"},
        headers=auth_header(token),
    )
    activate_missing = client.post(
        "/bots/00000000-0000-0000-0000-000000000000/activate",
        headers=auth_header(token),
    )

    assert create_response.status_code == 409
    assert activate_missing.status_code == 404


def test_multi_tenancy_and_platform_admin(runtime: Runtime) -> None:
    client = runtime.client
    org_a = create_organization(client, "acme")
    org_b = create_organization(client, "beta")
    create_user(client, org_a, "owner-a@example.com")
    create_user(client, org_b, "owner-b@example.com")
    token_a = login(client, "owner-a@example.com")
    token_b = login(client, "owner-b@example.com")
    bot_a = create_bot(client, token_a, {"slug": "bot-a"})
    create_bot(client, token_b, {"slug": "bot-b"})
    platform_user = create_user(client, org_a, "platform@example.com", token=token_a)
    platform_token = make_platform_admin(runtime, str(platform_user["email"]))

    cross_read = client.get(f"/bots/{bot_a['id']}", headers=auth_header(token_b))
    cross_update = client.patch(
        f"/bots/{bot_a['id']}",
        json={"name": "Blocked"},
        headers=auth_header(token_b),
    )
    tenant_list = client.get("/bots", headers=auth_header(token_a))
    platform_list = client.get("/bots", headers=auth_header(platform_token))
    platform_create = client.post(
        "/bots",
        json={"organization_id": org_b, "name": "Platform Bot", "slug": "platform"},
        headers=auth_header(platform_token),
    )

    assert cross_read.status_code == 403
    assert cross_update.status_code == 403
    assert tenant_list.status_code == 200
    assert tenant_list.json()["total"] == 1
    assert platform_list.status_code == 200
    assert platform_list.json()["total"] == 2
    assert platform_create.status_code == 201


def test_viewer_and_operator_are_read_only(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    viewer = create_user(client, org, "viewer@example.com", token=owner_token)
    operator = create_user(
        client,
        org,
        "operator@example.com",
        token=owner_token,
        role="operator",
    )
    bot = create_bot(client, owner_token)
    viewer_token = login(client, str(viewer["email"]))
    operator_token = login(client, str(operator["email"]))

    viewer_read = client.get(f"/bots/{bot['id']}", headers=auth_header(viewer_token))
    viewer_update = client.patch(
        f"/bots/{bot['id']}",
        json={"name": "Nope"},
        headers=auth_header(viewer_token),
    )
    operator_create = client.post(
        "/bots",
        json={"name": "Nope", "slug": "nope"},
        headers=auth_header(operator_token),
    )

    assert viewer_read.status_code == 200
    assert viewer_update.status_code == 403
    assert operator_create.status_code == 403


def test_update_rejects_organization_id_change(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    bot = create_bot(client, token)

    response = client.patch(
        f"/bots/{bot['id']}",
        json={"organization_id": org},
        headers=auth_header(token),
    )

    assert response.status_code == 403


def test_prd_regressions(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    owner = create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")

    me = client.get("/auth/me", headers=auth_header(token))
    roles = client.get("/roles", headers=auth_header(token))
    org_response = client.get(f"/organizations/{org}", headers=auth_header(token))

    assert owner["role"] == "organization_owner"
    assert me.status_code == 200
    assert roles.status_code == 200
    assert "bots.create" in roles.json()["roles"][1]["permissions"]
    assert org_response.status_code == 200
