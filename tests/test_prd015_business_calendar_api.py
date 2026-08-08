from collections.abc import Generator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.api.business_calendar_dependencies import get_business_calendar_service
from app.api.business_calendar_routes import router
from app.api.dependencies import require_authenticated_user
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.business_calendar import (
    BusinessCalendarAuditEventModel,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.test_prd015_business_calendar_service import _setup


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db = sessionmaker(bind=engine)()
    Base.metadata.create_all(engine)
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _client(session: Session) -> tuple[TestClient, dict[str, User], UUID]:
    service, actor, organization_id, _bot_id = _setup(session)
    actors = {"current": actor}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_business_calendar_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = lambda: actors["current"]
    return TestClient(app), actors, organization_id


def _create(client: TestClient, organization_id: UUID) -> dict[str, object]:
    response = client.post(
        f"/organizations/{organization_id}/business-calendars",
        json={"name": "Support", "timezone": "America/Lima"},
        headers={"Idempotency-Key": "api-calendar-create-001"},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def test_business_calendar_management_and_resolution_api(session: Session) -> None:
    client, _actors, organization_id = _client(session)
    created = _create(client, organization_id)
    calendar_id = str(created["id"])

    schedule = client.put(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/weekly-schedule",
        json={
            "expected_version": created["version"],
            "days": [
                {
                    "weekday": 1,
                    "intervals": [{"start": "09:00", "end": "17:00"}],
                }
            ],
        },
        headers={"Idempotency-Key": "api-weekly-001"},
    )
    assert schedule.status_code == 200, schedule.text

    holiday = client.post(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/holidays",
        json={
            "local_date": "2026-08-10",
            "name": "Local holiday",
            "scope": "full_day",
        },
        headers={"Idempotency-Key": "api-holiday-001"},
    )
    assert holiday.status_code == 201, holiday.text

    exception = client.post(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/date-exceptions",
        json={
            "local_date": "2026-08-10",
            "mode": "add_open",
            "intervals": [{"start": "10:00", "end": "12:00"}],
        },
        headers={"Idempotency-Key": "api-exception-001"},
    )
    assert exception.status_code == 201, exception.text

    activated = client.post(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/activate"
    )
    assert activated.status_code == 200, activated.text

    resolution = client.get(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/resolve",
        params={"at": "2026-08-10T15:30:00Z"},
    )
    assert resolution.status_code == 200, resolution.text
    assert resolution.json()["state"] == "open"
    assert resolution.json()["winning_rule_type"] == "date_exception"
    assert resolution.json()["local_date"] == "2026-08-10"
    assert resolution.json()["local_time"].startswith("10:30:00")

    audit_actions = set(
        session.scalars(select(BusinessCalendarAuditEventModel.action)).all()
    )
    assert audit_actions >= {
        "calendar.created",
        "weekly_schedule.replaced",
        "holiday.created",
        "date_exception.created",
        "calendar.activated",
    }


def test_api_rbac_grants_operator_read_and_resolve_only(session: Session) -> None:
    client, actors, organization_id = _client(session)
    created = _create(client, organization_id)
    calendar_id = str(created["id"])
    assert (
        client.post(
            f"/organizations/{organization_id}/business-calendars/"
            f"{calendar_id}/activate"
        ).status_code
        == 200
    )

    actors["current"] = User(
        id=uuid4(),
        organization_id=organization_id,
        email="operator@example.com",
        role="operator",
    )
    listing = client.get(f"/organizations/{organization_id}/business-calendars")
    assert listing.status_code == 200
    resolved = client.get(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/resolve",
        params={"at": datetime(2026, 8, 10, 15, tzinfo=UTC).isoformat()},
    )
    assert resolved.status_code == 200
    forbidden = client.post(
        f"/organizations/{organization_id}/business-calendars/"
        f"{calendar_id}/overrides",
        json={
            "decision": "force_open",
            "starts_at": "2026-08-10T10:00:00-05:00",
            "ends_at": "2026-08-10T11:00:00-05:00",
            "reason": "Emergency coverage",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission denied"

    actors["current"] = User(
        id=uuid4(),
        organization_id=organization_id,
        email="viewer@example.com",
        role="viewer",
    )
    assert (
        client.get(f"/organizations/{organization_id}/business-calendars").status_code
        == 403
    )


def test_api_is_tenant_safe_and_maps_idempotency_conflicts(session: Session) -> None:
    client, actors, organization_id = _client(session)
    created = _create(client, organization_id)
    calendar_id = str(created["id"])

    replay = client.post(
        f"/organizations/{organization_id}/business-calendars",
        json={"name": "Support", "timezone": "America/Lima"},
        headers={"Idempotency-Key": "api-calendar-create-001"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == calendar_id

    conflict = client.post(
        f"/organizations/{organization_id}/business-calendars",
        json={"name": "Sales", "timezone": "UTC"},
        headers={"Idempotency-Key": "api-calendar-create-001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"

    foreign_org = uuid4()
    actors["current"] = User(
        id=uuid4(),
        organization_id=foreign_org,
        email="foreign-owner@example.com",
        role="organization_owner",
    )
    hidden = client.get(
        f"/organizations/{foreign_org}/business-calendars/{calendar_id}"
    )
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "BUSINESS_CALENDAR_NOT_FOUND"
