from collections.abc import Generator
from dataclasses import dataclass

import pytest
from app.api.dependencies import (
    get_bot_service,
    get_organization_service,
    get_user_service,
)
from app.api.knowledge_dependencies import get_knowledge_management_service
from app.application.bots.service import BotService
from app.application.knowledge_management.service import KnowledgeManagementService
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.infrastructure.database import Base
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
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

    def organization_service() -> OrganizationService:
        return OrganizationService(
            OrganizationRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            no_op_plan_repository(),
        )

    def user_service() -> UserService:
        return UserService(
            UserRepository(session),
            OrganizationRepository(session),
            password_service,
            session,
            SqlAlchemyAuditRepository(session),
            allow_all_plan_enforcement(),
        )

    def bot_service() -> BotService:
        return BotService(
            BotRepository(session),
            OrganizationRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            allow_all_plan_enforcement(),
        )

    def knowledge_service() -> KnowledgeManagementService:
        return KnowledgeManagementService(
            SqlAlchemyKnowledgeEntryRepository(session),
            BotRepository(session),
            OrganizationRepository(session),
            session,
            allow_all_plan_enforcement(),
            SqlAlchemyAuditRepository(session),
        )

    app = create_app()
    app.dependency_overrides[get_organization_service] = organization_service
    app.dependency_overrides[get_user_service] = user_service
    app.dependency_overrides[get_bot_service] = bot_service
    app.dependency_overrides[get_knowledge_management_service] = knowledge_service
    try:
        with TestClient(app) as client:
            yield Runtime(client, session)
    finally:
        session.close()
        app.dependency_overrides.clear()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_org(client: TestClient, slug: str) -> str:
    response = client.post("/organizations", json={"name": slug, "slug": slug})
    assert response.status_code == 201
    return str(response.json()["organization"]["id"])


def create_user(
    client: TestClient,
    organization_id: str,
    email: str,
    *,
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
    response = client.post(
        "/users",
        json=payload,
        headers=auth(token) if token else None,
    )
    assert response.status_code == 201
    return dict(response.json()["user"])


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "valid-password-123"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def create_bot(client: TestClient, token: str, slug: str) -> dict[str, object]:
    response = client.post(
        "/bots",
        json={"name": slug, "slug": slug},
        headers=auth(token),
    )
    assert response.status_code == 201
    return dict(response.json()["bot"])


def make_platform_admin(runtime: Runtime, email: str) -> str:
    model = UserRepository(runtime.session).find_by_email(email)
    assert model is not None
    model.role = "platform_admin"
    runtime.session.commit()
    return login(runtime.client, email)


def test_lifecycle_rbac_filters_and_pagination(runtime: Runtime) -> None:
    client = runtime.client
    organization_id = create_org(client, "acme")
    create_user(client, organization_id, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    operator = create_user(
        client,
        organization_id,
        "operator@example.com",
        token=owner_token,
        role="operator",
    )
    viewer = create_user(
        client,
        organization_id,
        "viewer@example.com",
        token=owner_token,
    )
    bot = create_bot(client, owner_token, "support")
    base = f"/organizations/{organization_id}/bots/{bot['id']}/knowledge"
    operator_token = login(client, str(operator["email"]))
    viewer_token = login(client, str(viewer["email"]))

    created_ids: list[str] = []
    for index in range(3):
        response = client.post(
            base,
            json={"title": f"Policy {index}", "content": f"Content {index}"},
            headers=auth(operator_token),
        )
        assert response.status_code == 201
        created_ids.append(response.json()["knowledge_entry"]["id"])

    page = client.get(
        f"{base}?status=draft&search=Policy&page=2&page_size=2",
        headers=auth(viewer_token),
    )
    operator_update = client.patch(
        f"{base}/{created_ids[1]}",
        json={"title": "Updated policy"},
        headers=auth(operator_token),
    )
    viewer_update = client.patch(
        f"{base}/{created_ids[0]}",
        json={"title": "Blocked"},
        headers=auth(viewer_token),
    )
    operator_publish = client.post(
        f"{base}/{created_ids[0]}/publish",
        headers=auth(operator_token),
    )
    published = client.post(
        f"{base}/{created_ids[0]}/publish",
        headers=auth(owner_token),
    )
    invalid_publish = client.post(
        f"{base}/{created_ids[0]}/publish",
        headers=auth(owner_token),
    )
    archived = client.post(
        f"{base}/{created_ids[0]}/archive",
        headers=auth(owner_token),
    )
    archived_update = client.patch(
        f"{base}/{created_ids[0]}",
        json={"content": "Blocked"},
        headers=auth(operator_token),
    )
    deleted = client.delete(
        f"{base}/{created_ids[2]}",
        headers=auth(owner_token),
    )
    deleted_read = client.get(
        f"{base}/{created_ids[2]}",
        headers=auth(owner_token),
    )

    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 1
    assert operator_update.status_code == 200
    assert operator_update.json()["knowledge_entry"]["title"] == "Updated policy"
    assert viewer_update.status_code == 403
    assert operator_publish.status_code == 403
    assert published.status_code == 200
    assert invalid_publish.status_code == 409
    assert archived.status_code == 200
    assert archived_update.status_code == 409
    assert deleted.status_code == 204
    assert deleted_read.status_code == 404


def test_tenant_isolation_platform_admin_and_inactive_user(runtime: Runtime) -> None:
    client = runtime.client
    org_a = create_org(client, "alpha")
    org_b = create_org(client, "beta")
    owner_a = create_user(client, org_a, "owner-a@example.com")
    create_user(client, org_b, "owner-b@example.com")
    token_a = login(client, str(owner_a["email"]))
    token_b = login(client, "owner-b@example.com")
    platform = create_user(
        client,
        org_a,
        "platform@example.com",
        token=token_a,
    )
    inactive_user = create_user(
        client,
        org_a,
        "inactive@example.com",
        token=token_a,
    )
    inactive_token = login(client, str(inactive_user["email"]))
    platform_token = make_platform_admin(runtime, str(platform["email"]))
    bot_a = create_bot(client, token_a, "alpha-bot")
    bot_b = create_bot(client, token_b, "beta-bot")
    base_a = f"/organizations/{org_a}/bots/{bot_a['id']}/knowledge"
    created = client.post(
        base_a,
        json={"title": "Private", "content": "Tenant A"},
        headers=auth(token_a),
    )
    entry_id = created.json()["knowledge_entry"]["id"]

    cross = client.get(f"{base_a}/{entry_id}", headers=auth(token_b))
    wrong_bot = client.get(
        f"/organizations/{org_a}/bots/{bot_b['id']}/knowledge/{entry_id}",
        headers=auth(token_a),
    )
    platform_read = client.get(
        f"{base_a}/{entry_id}",
        headers=auth(platform_token),
    )
    client.post(
        f"/users/{inactive_user['id']}/deactivate",
        headers=auth(platform_token),
    )
    inactive = client.get(base_a, headers=auth(inactive_token))

    assert cross.status_code == 403
    assert wrong_bot.status_code == 404
    assert platform_read.status_code == 200
    assert inactive.status_code == 403
