from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProviderStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"


class Capability(StrEnum):
    SEND_MESSAGE = "send_message"
    HTTP_REQUEST = "http_request"


class ExecutionStatusType(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidatedIntegrationRequest[T](BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    capability: Capability
    tenant_id: str
    payload: T
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntegrationRequest[T](BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    capability: Capability
    tenant_id: str
    payload: T
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    data: dict[str, object] | None = None
    provider_response: dict[str, object] | None = None
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntegrationError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str = ""
    details: dict[str, object] | None = None
    attempt: int = 0


class IntegrationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    capability: Capability
    success: bool
    response: IntegrationResponse | None = None
    error: IntegrationError | None = None
    attempts: int = 0
    latency_ms: int = 0
    circuit_breaker_open: bool = False
    rate_limited: bool = False
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntegrationEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: str
    capability: Capability
    provider_id: str
    tenant_id: str
    request_id: UUID
    success: bool
    latency_ms: int = 0
    attempt: int = 0
    error: IntegrationError | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Provider(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    name: str
    capability: Capability
    status: ProviderStatus = ProviderStatus.ACTIVE
    version: str = "1.0"


class ProviderContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: Provider
    base_url: str = ""
    credentials: "AuthCredential | None" = None
    config: "IntegrationConfiguration | None" = None
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthCredential(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = "bearer_token"
    value: str = ""
    expires_at: datetime | None = None


class IntegrationConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    tenant_id: str
    base_url: str = ""
    api_version: str = ""
    timeout_seconds: int = 30
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    rate_limit_max_per_second: int = 80
    rate_limit_bucket_size: int = 80
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 30
    headers: dict[str, str] = Field(default_factory=dict)


class IntegrationExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    request_id: UUID
    capability: Capability
    provider_id: str
    status: ExecutionStatusType = ExecutionStatusType.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int = 0
    result: IntegrationResult | None = None


class HealthCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    status: ProviderStatus
    latency_ms: int = 0
    error: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessagingPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: str
    to: str
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)


class MessagingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_message_id: str | None = None
    status: str = "sent"
    raw_response: dict[str, object] | None = None


class ProviderVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    version: str
    base_url: str = ""
    api_version: str = ""
    config_overrides: dict[str, object] = Field(default_factory=dict)


class ProviderVersionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    versions: list[ProviderVersion] = Field(default_factory=list)
    default_version: str = "1.0"
