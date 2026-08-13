from collections.abc import Generator
from dataclasses import dataclass

import pytest
from app.api.dependencies import (
    get_bot_service,
    get_business_configuration_service,
    get_organization_service,
    get_user_service,
)
from app.application.bots.service import BotService
from app.application.business_configuration.service import (
    BusinessConfigurationService,
)
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.infrastructure.database import Base
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.business_configuration_repository import (
    BusinessConfigurationRepository,
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

    def override_bot_service() -> BotService:
        return BotService(
            repository=BotRepository(session=session),
            organization_repository=OrganizationRepository(session=session),
            session=session,
            audit_writer=SqlAlchemyAuditRepository(session),
            plan_enforcement=allow_all_plan_enforcement(),
        )

    def override_business_configuration_service() -> BusinessConfigurationService:
        return BusinessConfigurationService(
            repository=BusinessConfigurationRepository(session=session),
            bot_repository=BotRepository(session=session),
            organization_repository=OrganizationRepository(session=session),
            session=session,
            audit_writer=SqlAlchemyAuditRepository(session),
        )

    app = create_app()
    app.dependency_overrides[get_organization_service] = override_organization_service
    app.dependency_overrides[get_user_service] = override_user_service
    app.dependency_overrides[get_bot_service] = override_bot_service
    app.dependency_overrides[get_business_configuration_service] = (
        override_business_configuration_service
    )
    try:
        with TestClient(app) as test_client:
            yield Runtime(client=test_client, session=session)
    finally:
        session.close()
        app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def business_hours() -> dict[str, dict[str, object]]:
    open_day: dict[str, object] = {
        "enabled": True,
        "open_time": "09:00",
        "close_time": "18:00",
    }
    closed_day: dict[str, object] = {"enabled": False}
    return {
        "monday": open_day,
        "tuesday": open_day,
        "wednesday": open_day,
        "thursday": open_day,
        "friday": open_day,
        "saturday": closed_day,
        "sunday": closed_day,
    }


def config_payload() -> dict[str, object]:
    return {
        "business_name": "Acme Support",
        "description": "Customer support for Acme.",
        "phone": "+51999999999",
        "email": "support@example.com",
        "website": "https://example.com",
        "address": "Lima",
        "timezone": "America/Lima",
        "business_hours": business_hours(),
        "services": [
            {
                "name": "Support",
                "description": "General support",
                "active": True,
                "price": 10,
                "currency": "PEN",
                "duration_minutes": 30,
            }
        ],
        "payment_methods": ["cash", "card"],
        "policies": [{"name": "Refunds", "description": "Case by case"}],
        "service_instructions": "Answer politely.",
        "handoff_enabled": True,
        "handoff_message": "A human will help you.",
        "handoff_keywords": ["human", "agent"],
        "handoff_outside_business_hours": True,
    }


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
        "slug": "support-bot",
        "default_language": "es",
        "timezone": "America/Lima",
    }
    if payload is not None:
        body.update(payload)
    response = client.post("/bots", json=body, headers=auth_header(token))
    assert response.status_code == 201
    return dict(response.json()["bot"])


def create_configuration(
    client: TestClient,
    token: str,
    bot_id: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    body = config_payload()
    if payload is not None:
        body.update(payload)
    response = client.post(
        f"/bots/{bot_id}/business-configuration",
        json=body,
        headers=auth_header(token),
    )
    assert response.status_code == 201
    return dict(response.json()["business_configuration"])


def test_create_get_update_business_configuration(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    bot = create_bot(client, token)

    config = create_configuration(client, token, str(bot["id"]))
    fetched = client.get(
        f"/bots/{bot['id']}/business-configuration",
        headers=auth_header(token),
    )
    updated = client.patch(
        f"/bots/{bot['id']}/business-configuration",
        json={
            "business_name": "Updated Acme",
            "timezone": "America/Bogota",
            "handoff_enabled": False,
            "handoff_keywords": ["asesor"],
        },
        headers=auth_header(token),
    )

    assert config["bot_id"] == bot["id"]
    assert config["status"] == "configured"
    assert fetched.status_code == 200
    assert fetched.json()["business_configuration"]["business_name"] == "Acme Support"
    assert updated.status_code == 200
    assert updated.json()["business_configuration"]["business_name"] == "Updated Acme"
    assert updated.json()["business_configuration"]["timezone"] == "America/Bogota"
    assert updated.json()["business_configuration"]["handoff_enabled"] is False


def test_missing_bot_duplicate_and_immutable_bot_id(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    bot = create_bot(client, token)
    create_configuration(client, token, str(bot["id"]))

    missing = client.post(
        "/bots/00000000-0000-0000-0000-000000000000/business-configuration",
        json=config_payload(),
        headers=auth_header(token),
    )
    duplicate = client.post(
        f"/bots/{bot['id']}/business-configuration",
        json=config_payload(),
        headers=auth_header(token),
    )
    immutable = client.patch(
        f"/bots/{bot['id']}/business-configuration",
        json={"bot_id": bot["id"]},
        headers=auth_header(token),
    )

    assert missing.status_code == 404
    assert duplicate.status_code == 409
    assert immutable.status_code == 403


def test_cross_tenant_and_platform_admin_access(runtime: Runtime) -> None:
    client = runtime.client
    org_a = create_organization(client, "acme")
    org_b = create_organization(client, "beta")
    create_user(client, org_a, "owner-a@example.com")
    create_user(client, org_b, "owner-b@example.com")
    token_a = login(client, "owner-a@example.com")
    token_b = login(client, "owner-b@example.com")
    bot_a = create_bot(client, token_a, {"slug": "bot-a"})
    bot_b = create_bot(client, token_b, {"slug": "bot-b"})
    create_configuration(client, token_a, str(bot_a["id"]))
    platform_user = create_user(client, org_a, "platform@example.com", token=token_a)
    platform_token = make_platform_admin(runtime, str(platform_user["email"]))

    cross_read = client.get(
        f"/bots/{bot_a['id']}/business-configuration",
        headers=auth_header(token_b),
    )
    cross_update = client.patch(
        f"/bots/{bot_a['id']}/business-configuration",
        json={"business_name": "Blocked"},
        headers=auth_header(token_b),
    )
    platform_create = client.post(
        f"/bots/{bot_b['id']}/business-configuration",
        json=config_payload(),
        headers=auth_header(platform_token),
    )
    platform_read = client.get(
        f"/bots/{bot_b['id']}/business-configuration",
        headers=auth_header(platform_token),
    )

    assert cross_read.status_code == 403
    assert cross_update.status_code == 403
    assert platform_create.status_code == 201
    assert platform_read.status_code == 200


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
    create_configuration(client, owner_token, str(bot["id"]))
    viewer_token = login(client, str(viewer["email"]))
    operator_token = login(client, str(operator["email"]))

    viewer_read = client.get(
        f"/bots/{bot['id']}/business-configuration",
        headers=auth_header(viewer_token),
    )
    viewer_update = client.patch(
        f"/bots/{bot['id']}/business-configuration",
        json={"business_name": "Nope"},
        headers=auth_header(viewer_token),
    )
    operator_create = client.post(
        f"/bots/{bot['id']}/business-configuration",
        json=config_payload(),
        headers=auth_header(operator_token),
    )

    assert viewer_read.status_code == 200
    assert viewer_update.status_code == 403
    assert operator_create.status_code == 403


def test_admin_can_write_and_inactive_organization_blocks_write(
    runtime: Runtime,
) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    owner_token = login(client, "owner@example.com")
    admin = create_user(
        client,
        org,
        "admin@example.com",
        token=owner_token,
        role="organization_admin",
    )
    bot = create_bot(client, owner_token)
    admin_token = login(client, str(admin["email"]))
    created = create_configuration(client, admin_token, str(bot["id"]))
    client.post(f"/organizations/{org}/deactivate", headers=auth_header(owner_token))

    read_after_deactivate = client.get(
        f"/bots/{bot['id']}/business-configuration",
        headers=auth_header(admin_token),
    )
    update_after_deactivate = client.patch(
        f"/bots/{bot['id']}/business-configuration",
        json={"business_name": "Blocked"},
        headers=auth_header(admin_token),
    )

    assert created["business_name"] == "Acme Support"
    assert read_after_deactivate.status_code == 403
    assert update_after_deactivate.status_code == 403


def test_bot_inactive_can_keep_and_read_configuration(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    bot = create_bot(client, token)
    create_configuration(client, token, str(bot["id"]))
    client.post(f"/bots/{bot['id']}/activate", headers=auth_header(token))
    client.post(f"/bots/{bot['id']}/deactivate", headers=auth_header(token))

    response = client.get(
        f"/bots/{bot['id']}/business-configuration",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["business_configuration"]["bot_id"] == bot["id"]


def test_validation_errors(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    bot = create_bot(client, token)

    for field, value in (
        ("timezone", "Mars/Base"),
        ("email", "invalid"),
        ("website", "ftp://example.com"),
    ):
        payload = config_payload()
        payload[field] = value
        response = client.post(
            f"/bots/{bot['id']}/business-configuration",
            json=payload,
            headers=auth_header(token),
        )
        assert response.status_code == 422

    payload = config_payload()
    hours = business_hours()
    hours["monday"] = {"enabled": True, "open_time": "18:00", "close_time": "09:00"}
    payload["business_hours"] = hours
    invalid_hours = client.post(
        f"/bots/{bot['id']}/business-configuration",
        json=payload,
        headers=auth_header(token),
    )

    payload = config_payload()
    payload["services"] = [{"name": "", "active": True}]
    invalid_service = client.post(
        f"/bots/{bot['id']}/business-configuration",
        json=payload,
        headers=auth_header(token),
    )

    assert invalid_hours.status_code == 422
    assert invalid_service.status_code == 422


def test_prd_regressions(runtime: Runtime) -> None:
    client = runtime.client
    org = create_organization(client, "acme")
    create_user(client, org, "owner@example.com")
    token = login(client, "owner@example.com")
    bot = create_bot(client, token)
    create_configuration(client, token, str(bot["id"]))

    me = client.get("/auth/me", headers=auth_header(token))
    roles = client.get("/roles", headers=auth_header(token))
    org_response = client.get(f"/organizations/{org}", headers=auth_header(token))
    bot_response = client.get(f"/bots/{bot['id']}", headers=auth_header(token))

    assert me.status_code == 200
    assert roles.status_code == 200
    assert "business_configuration.create" in roles.json()["roles"][1]["permissions"]
    assert org_response.status_code == 200
    assert bot_response.status_code == 200
