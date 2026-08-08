from dataclasses import dataclass
from typing import Protocol

from app.domain.integration_management.contracts import (
    AvailabilityRequest,
    CalendarAvailability,
    CalendarMetadata,
)


class IntegrationProviderError(RuntimeError):
    pass


class IntegrationProviderAuthError(IntegrationProviderError):
    pass


class IntegrationProviderUnreachableError(IntegrationProviderError):
    pass


class IntegrationProviderResponseError(IntegrationProviderError):
    pass


@dataclass(frozen=True)
class OAuthTokenResult:
    access_token: str
    refresh_token: str | None


class CalendarIntegrationAdapter(Protocol):
    provider: str

    def build_authorization_url(self, state: str) -> str: ...

    def exchange_authorization_code(self, code: str) -> OAuthTokenResult: ...

    def get_health(self, refresh_token: str) -> str | None: ...

    def get_health_with_access_token(self, access_token: str) -> None: ...

    def list_calendars(self, refresh_token: str) -> list[CalendarMetadata]: ...

    def get_calendar_metadata(
        self, refresh_token: str, calendar_id: str
    ) -> CalendarMetadata: ...

    def get_availability(
        self, refresh_token: str, request: AvailabilityRequest
    ) -> list[CalendarAvailability]: ...
