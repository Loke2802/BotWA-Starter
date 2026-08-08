from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.api.integration_management_dependencies import (
    get_integration_management_service,
)
from app.api.integration_management_routes import oauth_router, router
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.test_prd013_integration_management import _payload, _setup


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _client(session: Session) -> tuple[TestClient, dict[str, User], UUID]:
    service, _adapter, actor, organization_id, _bot_id = _setup(session)
    actors = {"current": actor}
    app = FastAPI()
    app.include_router(router)
    app.include_router(oauth_router)
    app.dependency_overrides[get_integration_management_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = lambda: actors["current"]
    return TestClient(app), actors, organization_id


def _create(client: TestClient, organization_id: UUID) -> str:
    response = client.post(
        f"/organizations/{organization_id}/integrations",
        json=_payload().model_dump(mode="json"),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_crud_lifecycle_credentials_and_health_api_never_returns_secret(
    session: Session,
) -> None:
    client, _actors, organization_id = _client(session)
    integration_id = _create(client, organization_id)
    listing = client.get(f"/organizations/{organization_id}/integrations")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    detail = client.get(
        f"/organizations/{organization_id}/integrations/{integration_id}"
    )
    assert detail.status_code == 200
    assert detail.json()["has_credentials"] is False

    credential = client.put(
        f"/organizations/{organization_id}/integrations/{integration_id}/credentials",
        json={"refresh_token": "api-refresh-token"},
    )
    assert credential.status_code == 200
    assert "api-refresh-token" not in credential.text
    assert "refresh_token" not in credential.json()

    activated = client.post(
        f"/organizations/{organization_id}/integrations/{integration_id}/activate"
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    health = client.post(
        f"/organizations/{organization_id}/integrations/{integration_id}/health-check"
    )
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    history = client.get(
        f"/organizations/{organization_id}/integrations/{integration_id}/health"
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert (
        client.post(
            f"/organizations/{organization_id}/integrations/{integration_id}/deactivate"
        ).json()["status"]
        == "inactive"
    )
    assert (
        client.post(
            f"/organizations/{organization_id}/integrations/{integration_id}/archive"
        ).json()["status"]
        == "archived"
    )


def test_api_rbac_and_cross_tenant_lookup_are_safe(session: Session) -> None:
    client, actors, organization_id = _client(session)
    integration_id = _create(client, organization_id)
    actors["current"] = User(
        id=uuid4(),
        organization_id=organization_id,
        email="viewer@example.com",
        role="viewer",
    )
    assert (
        client.get(f"/organizations/{organization_id}/integrations").status_code == 403
    )

    foreign_org = uuid4()
    actors["current"] = User(
        id=uuid4(),
        organization_id=foreign_org,
        email="foreign-owner@example.com",
        role="organization_owner",
    )
    response = client.get(f"/organizations/{foreign_org}/integrations/{integration_id}")
    assert response.status_code == 404
    assert "api-refresh-token" not in response.text


def test_public_oauth_callback_uses_state_only_and_rejects_replay(
    session: Session,
) -> None:
    client, _actors, organization_id = _client(session)
    integration_id = _create(client, organization_id)
    start = client.post(
        f"/organizations/{organization_id}/integrations/{integration_id}/oauth/google/start"
    )
    assert start.status_code == 200
    state = start.json()["authorization_url"].split("state=", maxsplit=1)[1]
    callback = client.get(
        "/integrations/oauth/google/callback",
        params={"state": state, "code": "one-time-code"},
    )
    assert callback.status_code == 200
    assert callback.json() == {"status": "connected"}
    replay = client.get(
        "/integrations/oauth/google/callback",
        params={"state": state, "code": "replayed-code"},
    )
    assert replay.status_code == 422
    assert replay.json()["detail"]["code"] == "OAUTH_STATE_REPLAYED"
