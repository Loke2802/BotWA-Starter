"""Guard the executable rehearsal against a non-synthetic target and false passes."""

from typing import Any
from uuid import uuid4

import httpx
import pytest
from scripts.verify_crm_journey_local import Journey, validate_target


def manifest() -> dict[str, Any]:
    return {
        "environment": "disposable local PostgreSQL",
        "databases": {"after": "luri_rehearsal_0123456789_after"},
        **{
            key: str(uuid4())
            for key in (
                "organization_id",
                "other_organization_id",
                "contact_id",
                "conversation_id",
            )
        },
        "accounts": {
            role: role + "@local-crm.example.test"
            for role in ("organization_owner", "operator", "viewer", "other_company")
        },
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://production.example:443",
        "http://192.168.1.1:8770",
        "https://127.0.0.1:8770",
        "http://secret@127.0.0.1:8770",
        "http://127.0.0.1:8770/portal",
        "http://127.0.0.1:8770?target=remote",
        "http://localhost",
    ],
)
def test_journey_refuses_nonlocal_or_ambiguous_target(url: str) -> None:
    with pytest.raises(ValueError, match="localhost"):
        validate_target(url, manifest())


@pytest.mark.parametrize("change", ["environment", "database", "account"])
def test_journey_requires_synthetic_manifest(change: str) -> None:
    data = manifest()
    if change == "environment":
        data["environment"] = "production"
    elif change == "database":
        data["databases"]["after"] = "real_customers"
    else:
        data["accounts"]["viewer"] = "person@example.com"
    with pytest.raises(ValueError, match="synthetic"):
        validate_target("http://127.0.0.1:8770", data)


def test_unexpected_http_status_fails_without_exporting_response_secrets() -> None:
    journey = Journey("http://127.0.0.1:8770", manifest())
    journey.client.close()
    journey.client = httpx.Client(
        base_url=journey.base_url,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={"detail": "private-secret"})
        ),
    )
    try:
        with pytest.raises(AssertionError, match="expected 200, got 500") as failure:
            journey.request("GET", "/broken")
        assert "private-secret" not in str(failure.value)
        assert not journey.report["checks"] and journey.report["status"] == "running"
    finally:
        journey.client.close()
