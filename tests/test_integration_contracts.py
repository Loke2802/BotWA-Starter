from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.domain.integration.contracts import (
    AuthCredential,
    Capability,
    ExecutionStatusType,
    HealthCheckResult,
    IntegrationConfiguration,
    IntegrationError,
    IntegrationEvent,
    IntegrationExecution,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationResult,
    MessagingPayload,
    MessagingResponse,
    Provider,
    ProviderContext,
    ProviderStatus,
    ValidatedIntegrationRequest,
)
from pydantic import ValidationError


def mutate_field(target: object, field: str, value: object) -> None:
    setattr(target, field, value)


class TestCapability:
    def test_capability_values(self) -> None:
        assert Capability.SEND_MESSAGE.value == "send_message"
        assert Capability.HTTP_REQUEST.value == "http_request"

    def test_capability_is_enum(self) -> None:
        assert issubclass(Capability, str)


class TestProvider:
    def test_provider_defaults(self) -> None:
        p = Provider(
            provider_id="wa-1", name="WhatsApp", capability=Capability.SEND_MESSAGE
        )
        assert p.status == ProviderStatus.ACTIVE
        assert p.version == "1.0"

    def test_provider_custom_version(self) -> None:
        p = Provider(
            provider_id="wa-2",
            name="WhatsApp",
            capability=Capability.SEND_MESSAGE,
            version="v22.0",
        )
        assert p.version == "v22.0"

    def test_provider_is_frozen(self) -> None:
        p = Provider(provider_id="p1", name="Test", capability=Capability.HTTP_REQUEST)
        with pytest.raises(ValidationError):
            mutate_field(p, "provider_id", "p2")


class TestIntegrationRequest:
    def test_required_fields(self) -> None:
        req = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="tenant-1",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message="Hello"
            ),
        )
        assert req.capability == Capability.SEND_MESSAGE
        assert req.payload.channel == "whatsapp"
        assert isinstance(req.created_at, datetime)

    def test_generates_created_at(self) -> None:
        req = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.HTTP_REQUEST,
            tenant_id="t1",
            payload=MessagingPayload(channel="http", to="", message=""),
        )
        assert req.created_at.tzinfo is UTC

    def test_is_frozen(self) -> None:
        req = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=MessagingPayload(channel="w", to="1", message="hi"),
        )
        with pytest.raises(ValidationError):
            mutate_field(req, "tenant_id", "t2")


class TestValidatedIntegrationRequest:
    def test_holds_all_fields(self) -> None:
        payload = MessagingPayload(channel="w", to="1", message="hi")
        v = ValidatedIntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=payload,
        )
        assert v.payload.message == "hi"


class TestIntegrationResponse:
    def test_defaults(self) -> None:
        r = IntegrationResponse(success=True)
        assert r.success is True
        assert r.data is None
        assert r.normalized_at.tzinfo is UTC

    def test_with_data(self) -> None:
        r = IntegrationResponse(success=True, data={"message_id": "abc123"})
        assert r.data is not None
        assert r.data["message_id"] == "abc123"


class TestIntegrationError:
    def test_holds_code_and_message(self) -> None:
        e = IntegrationError(code="TIMEOUT", message="Request timed out")
        assert e.code == "TIMEOUT"
        assert e.attempt == 0

    def test_with_details(self) -> None:
        e = IntegrationError(code="AUTH_FAILED", details={"status_code": 401})
        assert e.details is not None
        assert e.details["status_code"] == 401


class TestIntegrationResult:
    def test_success_result(self) -> None:
        response = IntegrationResponse(success=True, data={"ok": True})
        result = IntegrationResult(
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            success=True,
            response=response,
            attempts=1,
            latency_ms=150,
        )
        assert result.success is True
        assert result.attempts == 1
        assert result.latency_ms == 150
        assert result.circuit_breaker_open is False

    def test_failure_result(self) -> None:
        error = IntegrationError(
            code="PROVIDER_UNAVAILABLE", message="Connection refused"
        )
        result = IntegrationResult(
            request_id=uuid4(),
            capability=Capability.HTTP_REQUEST,
            success=False,
            error=error,
            attempts=3,
        )
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "PROVIDER_UNAVAILABLE"

    def test_default_values(self) -> None:
        result = IntegrationResult(
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            success=True,
        )
        assert result.attempts == 0
        assert result.latency_ms == 0
        assert result.finished_at.tzinfo is UTC


class TestIntegrationEvent:
    def test_required_fields(self) -> None:
        event = IntegrationEvent(
            event_id=uuid4(),
            event_type="integration.completed",
            capability=Capability.SEND_MESSAGE,
            provider_id="wa-1",
            tenant_id="t1",
            request_id=uuid4(),
            success=True,
        )
        assert event.event_type == "integration.completed"
        assert event.success is True

    def test_with_error(self) -> None:
        error = IntegrationError(code="TIMEOUT")
        event = IntegrationEvent(
            event_id=uuid4(),
            event_type="integration.failed",
            capability=Capability.HTTP_REQUEST,
            provider_id="http-1",
            tenant_id="t1",
            request_id=uuid4(),
            success=False,
            error=error,
        )
        assert event.error is not None
        assert event.error.code == "TIMEOUT"


class TestProviderContext:
    def test_holds_provider_and_config(self) -> None:
        provider = Provider(
            provider_id="wa-1", name="WhatsApp", capability=Capability.SEND_MESSAGE
        )
        ctx = ProviderContext(provider=provider, base_url="https://graph.facebook.com")
        assert ctx.provider.provider_id == "wa-1"
        assert ctx.base_url == "https://graph.facebook.com"
        assert ctx.resolved_at.tzinfo is UTC

    def test_defaults(self) -> None:
        provider = Provider(
            provider_id="p1", name="P1", capability=Capability.HTTP_REQUEST
        )
        ctx = ProviderContext(provider=provider)
        assert ctx.base_url == ""
        assert ctx.credentials is None


class TestAuthCredential:
    def test_default_type(self) -> None:
        cred = AuthCredential(value="token-123")
        assert cred.type == "bearer_token"
        assert cred.value == "token-123"

    def test_custom_type(self) -> None:
        cred = AuthCredential(type="api_key", value="key-456")
        assert cred.type == "api_key"


class TestIntegrationConfiguration:
    def test_defaults(self) -> None:
        cfg = IntegrationConfiguration(provider_id="wa-1", tenant_id="t1")
        assert cfg.timeout_seconds == 30
        assert cfg.retry_max_attempts == 3
        assert cfg.rate_limit_max_per_second == 80
        assert cfg.api_version == ""

    def test_custom_api_version(self) -> None:
        cfg = IntegrationConfiguration(
            provider_id="wa-1", tenant_id="t1", api_version="v23.0"
        )
        assert cfg.api_version == "v23.0"

    def test_custom_timeout(self) -> None:
        cfg = IntegrationConfiguration(
            provider_id="wa-1", tenant_id="t1", timeout_seconds=15
        )
        assert cfg.timeout_seconds == 15


class TestIntegrationExecution:
    def test_default_status(self) -> None:
        execution = IntegrationExecution(
            execution_id=uuid4(),
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            provider_id="wa-1",
        )
        assert execution.status == ExecutionStatusType.PENDING

    def test_with_result(self) -> None:
        result = IntegrationResult(
            request_id=uuid4(), capability=Capability.SEND_MESSAGE, success=True
        )
        execution = IntegrationExecution(
            execution_id=uuid4(),
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            provider_id="wa-1",
            status=ExecutionStatusType.COMPLETED,
            result=result,
            attempts=1,
        )
        assert execution.status == ExecutionStatusType.COMPLETED
        assert execution.result is not None


class TestHealthCheckResult:
    def test_active_health(self) -> None:
        hc = HealthCheckResult(
            provider_id="wa-1", status=ProviderStatus.ACTIVE, latency_ms=120
        )
        assert hc.status == ProviderStatus.ACTIVE
        assert hc.latency_ms == 120

    def test_failed_health(self) -> None:
        hc = HealthCheckResult(
            provider_id="wa-1",
            status=ProviderStatus.DEGRADED,
            error="Connection refused",
        )
        assert hc.status == ProviderStatus.DEGRADED
        assert hc.error == "Connection refused"


class TestMessagingModels:
    def test_messaging_payload(self) -> None:
        payload = MessagingPayload(
            channel="whatsapp", to="5511999999999", message="Hello!"
        )
        assert payload.channel == "whatsapp"
        assert payload.to == "5511999999999"
        assert payload.message == "Hello!"

    def test_messaging_response(self) -> None:
        resp = MessagingResponse(provider_message_id="msg-123", status="sent")
        assert resp.provider_message_id == "msg-123"
        assert resp.status == "sent"
