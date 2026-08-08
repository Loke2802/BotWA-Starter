from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.application.integration_management.providers import (
    IntegrationProviderAuthError,
    IntegrationProviderResponseError,
    IntegrationProviderUnreachableError,
)
from app.domain.integration_management.contracts import AvailabilityRequest
from app.infrastructure.integrations.google_calendar import (
    GOOGLE_CALENDAR_SCOPES,
    GoogleCalendarAdapter,
)


def _adapter(transport: httpx.BaseTransport) -> GoogleCalendarAdapter:
    return GoogleCalendarAdapter(
        client_id="test-client-id",
        client_secret="test-server-secret",
        redirect_uri="https://luri.example/integrations/oauth/google/callback",
        timeout_seconds=1,
        transport=transport,
    )


def test_authorization_url_uses_offline_access_signed_state_and_minimal_scopes() -> (
    None
):
    adapter = _adapter(httpx.MockTransport(lambda _: httpx.Response(500)))
    url = adapter.build_authorization_url("signed-state")
    query = parse_qs(urlparse(url).query)
    assert query["state"] == ["signed-state"]
    assert query["access_type"] == ["offline"]
    assert query["response_type"] == ["code"]
    assert set(query["scope"][0].split()) == set(GOOGLE_CALENDAR_SCOPES)
    assert all("write" not in scope for scope in GOOGLE_CALENDAR_SCOPES)


def test_exchange_code_returns_tokens_without_raw_provider_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://oauth2.googleapis.com/token"
        return httpx.Response(
            200,
            json={
                "access_token": "short-lived",
                "refresh_token": "long-lived",
                "expires_in": 3600,
                "unexpected": {"raw": "ignored"},
            },
        )

    result = _adapter(httpx.MockTransport(handler)).exchange_authorization_code(
        "authorization-code"
    )
    assert result.access_token == "short-lived"
    assert result.refresh_token == "long-lived"
    assert not hasattr(result, "unexpected")


def test_exchange_rejects_empty_refresh_token() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, json={"access_token": "ephemeral", "refresh_token": ""}
        )
    )

    with pytest.raises(IntegrationProviderResponseError):
        _adapter(transport).exchange_authorization_code("authorization-code")


def test_health_returns_rotated_refresh_token_without_exposing_provider_payload() -> (
    None
):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "access_token": "ephemeral",
                    "refresh_token": "rotated-refresh",
                    "unexpected": "ignored",
                },
            )
        assert request.headers["Authorization"] == "Bearer ephemeral"
        return httpx.Response(200, json={"items": []})

    rotated_refresh_token = _adapter(httpx.MockTransport(handler)).get_health(
        "original-refresh"
    )

    assert rotated_refresh_token == "rotated-refresh"


def test_list_metadata_refreshes_token_and_returns_canonical_models() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "ephemeral"})
        assert request.headers["Authorization"] == "Bearer ephemeral"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "primary",
                        "summary": "Primary",
                        "timeZone": "America/Lima",
                        "primary": True,
                        "accessRole": "owner",
                        "description": "not propagated",
                    }
                ]
            },
        )

    calendars = _adapter(httpx.MockTransport(handler)).list_calendars("refresh")
    assert len(calls) == 2
    assert calendars[0].calendar_id == "primary"
    assert calendars[0].display_name == "Primary"
    assert not hasattr(calendars[0], "description")


def test_availability_returns_busy_intervals_without_event_content() -> None:
    now = datetime.now(UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "ephemeral"})
        return httpx.Response(
            200,
            json={
                "calendars": {
                    "primary": {
                        "busy": [
                            {
                                "start": now.isoformat(),
                                "end": (now + timedelta(minutes=30)).isoformat(),
                                "summary": "must be ignored",
                            }
                        ]
                    }
                }
            },
        )

    result = _adapter(httpx.MockTransport(handler)).get_availability(
        "refresh",
        AvailabilityRequest(
            calendar_ids=["primary"],
            start=now,
            end=now + timedelta(hours=1),
            timezone="America/Lima",
        ),
    )
    assert len(result) == 1
    assert len(result[0].busy) == 1
    assert not hasattr(result[0].busy[0], "summary")


@pytest.mark.parametrize("status_code", [400, 401, 403])
def test_token_auth_failures_map_to_safe_exception(status_code: int) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(status_code, text="sensitive provider body")
    )
    with pytest.raises(IntegrationProviderAuthError) as error:
        _adapter(transport).exchange_authorization_code("code")
    assert "sensitive provider body" not in str(error.value)


def test_timeout_maps_to_unreachable_without_request_details() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive timeout details", request=request)

    with pytest.raises(IntegrationProviderUnreachableError) as error:
        _adapter(httpx.MockTransport(timeout)).get_health("refresh")
    assert "sensitive timeout details" not in str(error.value)


@pytest.mark.parametrize(
    "response", [httpx.Response(500), httpx.Response(200, text="bad")]
)
def test_provider_and_malformed_responses_are_safely_mapped(
    response: httpx.Response,
) -> None:
    with pytest.raises(IntegrationProviderResponseError):
        _adapter(httpx.MockTransport(lambda _: response)).get_health("refresh")
