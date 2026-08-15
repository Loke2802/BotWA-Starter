from collections.abc import Mapping
from datetime import datetime
from typing import cast
from urllib.parse import quote, urlencode

import httpx

from app.application.integration_management.providers import (
    IntegrationProviderAuthError,
    IntegrationProviderResponseError,
    IntegrationProviderUnreachableError,
    OAuthTokenResult,
)
from app.domain.integration_management.contracts import (
    AvailabilityRequest,
    BusyInterval,
    CalendarAvailability,
    CalendarMetadata,
)
from app.observability.metrics import ProviderObservation

GOOGLE_CALENDAR_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
)


class GoogleCalendarAdapter:
    provider = "google_calendar"
    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    calendar_api_base = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._timeout = timeout_seconds
        self._transport = transport

    def _require_server_configuration(self) -> None:
        if not self._client_id or not self._client_secret or not self._redirect_uri:
            raise IntegrationProviderResponseError(
                "google oauth server configuration is unavailable"
            )

    def build_authorization_url(self, state: str) -> str:
        self._require_server_configuration()
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"{self.authorization_endpoint}?{query}"

    def exchange_authorization_code(self, code: str) -> OAuthTokenResult:
        self._require_server_configuration()
        payload = self._request_json(
            "POST",
            self.token_endpoint,
            operation="oauth_exchange",
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            },
            auth_failure=True,
        )
        access_token = self._required_string(payload, "access_token")
        refresh_value = payload.get("refresh_token")
        if refresh_value is not None and (
            not isinstance(refresh_value, str) or not refresh_value
        ):
            raise IntegrationProviderResponseError("invalid oauth token response")
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=refresh_value,
        )

    def _refresh_access_token(self, refresh_token: str) -> OAuthTokenResult:
        self._require_server_configuration()
        payload = self._request_json(
            "POST",
            self.token_endpoint,
            operation="refresh_token",
            data={
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
            auth_failure=True,
        )
        access_token = self._required_string(payload, "access_token")
        refresh_value = payload.get("refresh_token")
        if refresh_value is not None and (
            not isinstance(refresh_value, str) or not refresh_value
        ):
            raise IntegrationProviderResponseError("invalid oauth token response")
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=refresh_value,
        )

    def get_health(self, refresh_token: str) -> str | None:
        tokens = self._refresh_access_token(refresh_token)
        self.get_health_with_access_token(tokens.access_token)
        return tokens.refresh_token

    def get_health_with_access_token(self, access_token: str) -> None:
        payload = self._authorized_json(
            "GET",
            f"{self.calendar_api_base}/users/me/calendarList",
            access_token,
            params={"maxResults": "1"},
            operation="health_check",
        )
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise IntegrationProviderResponseError("invalid calendar response")

    def list_calendars(self, refresh_token: str) -> list[CalendarMetadata]:
        access_token = self._refresh_access_token(refresh_token).access_token
        payload = self._authorized_json(
            "GET",
            f"{self.calendar_api_base}/users/me/calendarList",
            access_token,
            params={"maxResults": "250"},
            operation="calendar_list",
        )
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise IntegrationProviderResponseError("invalid calendar response")
        calendars: list[CalendarMetadata] = []
        for item in items:
            if not isinstance(item, dict):
                raise IntegrationProviderResponseError("invalid calendar response")
            calendars.append(self._calendar_metadata(item))
        return calendars

    def get_calendar_metadata(
        self, refresh_token: str, calendar_id: str
    ) -> CalendarMetadata:
        access_token = self._refresh_access_token(refresh_token).access_token
        encoded_calendar_id = quote(calendar_id, safe="")
        payload = self._authorized_json(
            "GET",
            f"{self.calendar_api_base}/users/me/calendarList/{encoded_calendar_id}",
            access_token,
            operation="calendar_list",
        )
        return self._calendar_metadata(payload)

    def get_availability(
        self, refresh_token: str, request: AvailabilityRequest
    ) -> list[CalendarAvailability]:
        access_token = self._refresh_access_token(refresh_token).access_token
        body: dict[str, object] = {
            "timeMin": request.start.isoformat(),
            "timeMax": request.end.isoformat(),
            "items": [{"id": calendar_id} for calendar_id in request.calendar_ids],
        }
        if request.timezone is not None:
            body["timeZone"] = request.timezone
        payload = self._authorized_json(
            "POST",
            f"{self.calendar_api_base}/freeBusy",
            access_token,
            json=body,
            operation="free_busy",
        )
        calendars = payload.get("calendars")
        if not isinstance(calendars, dict):
            raise IntegrationProviderResponseError("invalid availability response")
        results: list[CalendarAvailability] = []
        for calendar_id in request.calendar_ids:
            raw_calendar = calendars.get(calendar_id)
            if not isinstance(raw_calendar, dict):
                raise IntegrationProviderResponseError("invalid availability response")
            raw_errors = raw_calendar.get("errors")
            if isinstance(raw_errors, list) and raw_errors:
                raise IntegrationProviderResponseError(
                    "calendar availability unavailable"
                )
            raw_busy = raw_calendar.get("busy", [])
            if not isinstance(raw_busy, list):
                raise IntegrationProviderResponseError("invalid availability response")
            busy: list[BusyInterval] = []
            for raw_interval in raw_busy:
                if not isinstance(raw_interval, dict):
                    raise IntegrationProviderResponseError(
                        "invalid availability response"
                    )
                start = self._required_string(raw_interval, "start")
                end = self._required_string(raw_interval, "end")
                try:
                    busy.append(
                        BusyInterval(
                            start=datetime.fromisoformat(start.replace("Z", "+00:00")),
                            end=datetime.fromisoformat(end.replace("Z", "+00:00")),
                        )
                    )
                except ValueError as exc:
                    raise IntegrationProviderResponseError(
                        "invalid availability response"
                    ) from exc
            results.append(
                CalendarAvailability(start=request.start, end=request.end, busy=busy)
            )
        return results

    def _calendar_metadata(self, payload: Mapping[str, object]) -> CalendarMetadata:
        calendar_id = self._required_string(payload, "id")
        display_name = self._required_string(payload, "summary")
        timezone = payload.get("timeZone")
        access_role = payload.get("accessRole")
        primary = payload.get("primary", False)
        if timezone is not None and not isinstance(timezone, str):
            raise IntegrationProviderResponseError("invalid calendar response")
        if access_role is not None and not isinstance(access_role, str):
            raise IntegrationProviderResponseError("invalid calendar response")
        if not isinstance(primary, bool):
            raise IntegrationProviderResponseError("invalid calendar response")
        return CalendarMetadata(
            calendar_id=calendar_id,
            display_name=display_name,
            timezone=timezone,
            primary=primary,
            access_role=access_role,
        )

    @staticmethod
    def _required_string(payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise IntegrationProviderResponseError("invalid provider response")
        return value

    def _authorized_json(
        self,
        method: str,
        url: str,
        access_token: str,
        *,
        operation: str,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._request_json(
            method,
            url,
            operation=operation,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            json=json,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        operation: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        json: Mapping[str, object] | None = None,
        auth_failure: bool = False,
    ) -> dict[str, object]:
        observation = ProviderObservation("google_calendar", operation)
        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json,
                )
        except httpx.TimeoutException as exc:
            observation.finish("timeout")
            raise IntegrationProviderUnreachableError(
                "integration provider unreachable"
            ) from exc
        except httpx.RequestError as exc:
            observation.finish("network_error")
            raise IntegrationProviderUnreachableError(
                "integration provider unreachable"
            ) from exc
        if response.status_code in {400, 401, 403} and (
            auth_failure or response.status_code in {401, 403}
        ):
            observation.finish("auth_error")
            raise IntegrationProviderAuthError("integration authentication failed")
        if response.status_code >= 400:
            observation.finish(
                "rate_limited"
                if response.status_code == 429
                else "provider_error" if response.status_code >= 500 else "rejected"
            )
            raise IntegrationProviderResponseError("integration provider failed")
        try:
            raw = response.json()
        except ValueError as exc:
            observation.finish("invalid_response")
            raise IntegrationProviderResponseError("invalid provider response") from exc
        if not isinstance(raw, dict):
            observation.finish("invalid_response")
            raise IntegrationProviderResponseError("invalid provider response")
        observation.finish("success")
        return cast(dict[str, object], raw)
