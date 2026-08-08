from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

IntegrationType = Literal["calendar", "crm", "erp", "custom_api"]
IntegrationProvider = Literal["google_calendar"]
IntegrationStatus = Literal["draft", "active", "inactive", "archived"]
IntegrationHealthStatus = Literal[
    "unknown", "healthy", "degraded", "unreachable", "auth_error"
]
IntegrationCapability = Literal["calendar.metadata.read", "calendar.availability.read"]
SafeIntegrationErrorCode = Literal[
    "INTEGRATION_AUTH_REQUIRED",
    "INTEGRATION_AUTH_FAILED",
    "INTEGRATION_UNREACHABLE",
    "INTEGRATION_PROVIDER_ERROR",
    "INTEGRATION_CONFIGURATION_INVALID",
    "INTEGRATION_NOT_ACTIVE",
    "INTEGRATION_CREDENTIAL_INVALID",
    "OAUTH_STATE_INVALID",
    "OAUTH_STATE_EXPIRED",
    "OAUTH_STATE_REPLAYED",
]

GOOGLE_CALENDAR_CAPABILITIES: frozenset[str] = frozenset(
    {"calendar.metadata.read", "calendar.availability.read"}
)


class GoogleCalendarConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    calendar_id: str | None = Field(default=None, min_length=1, max_length=500)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    read_only: Literal[True] = True


class IntegrationConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    bot_id: UUID | None = None
    integration_type: IntegrationType
    provider: IntegrationProvider
    capabilities: list[IntegrationCapability] = Field(min_length=1, max_length=10)
    configuration: GoogleCalendarConfiguration = Field(
        default_factory=GoogleCalendarConfiguration
    )

    @model_validator(mode="after")
    def validate_provider_contract(self) -> "IntegrationConnectionCreate":
        if self.provider == "google_calendar" and self.integration_type != "calendar":
            raise ValueError("google_calendar requires calendar integration type")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("capabilities must not contain duplicates")
        if not set(self.capabilities).issubset(GOOGLE_CALENDAR_CAPABILITIES):
            raise ValueError("capability is not allowed for provider")
        return self


class IntegrationConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    bot_id: UUID | None = None
    capabilities: list[IntegrationCapability] | None = Field(
        default=None, min_length=1, max_length=10
    )
    configuration: GoogleCalendarConfiguration | None = None

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(
        cls, value: list[IntegrationCapability] | None
    ) -> list[IntegrationCapability] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("capabilities must not contain duplicates")
        return value


class IntegrationConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    organization_id: UUID
    bot_id: UUID | None
    name: str
    description: str | None
    integration_type: IntegrationType
    provider: IntegrationProvider
    status: IntegrationStatus
    version: int
    capabilities: list[IntegrationCapability]
    configuration: GoogleCalendarConfiguration
    health_status: IntegrationHealthStatus
    last_health_checked_at: datetime | None
    has_credentials: bool = False
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    deactivated_at: datetime | None
    archived_at: datetime | None


class IntegrationConnectionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[IntegrationConnectionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class IntegrationCredentialInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credential_type: Literal["google_oauth_refresh"] = "google_oauth_refresh"
    refresh_token: SecretStr = Field(min_length=1, max_length=8192)


class IntegrationCredentialResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    integration_id: UUID
    credential_type: str
    configured: bool
    rotated_at: datetime | None


class IntegrationHealthCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    integration_connection_id: UUID
    status: IntegrationHealthStatus
    safe_error_code: SafeIntegrationErrorCode | None
    checked_at: datetime
    latency_ms: int | None


class IntegrationHealthListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[IntegrationHealthCheckResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class OAuthStartResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_url: str
    expires_at: datetime


class OAuthCallbackResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["connected"] = "connected"


class CalendarMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    calendar_id: str
    display_name: str
    timezone: str | None
    primary: bool
    access_role: str | None


class BusyInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime


class CalendarAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime
    end: datetime
    busy: list[BusyInterval]


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    calendar_ids: list[str] = Field(min_length=1, max_length=50)
    start: datetime
    end: datetime
    timezone: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def valid_window(self) -> "AvailabilityRequest":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("availability datetimes must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("availability start must precede end")
        if any(not calendar_id.strip() for calendar_id in self.calendar_ids):
            raise ValueError("calendar ids cannot be empty")
        return self
