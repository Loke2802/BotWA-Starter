from uuid import uuid4

import pytest
from app.core.integration.gateway import IntegrationGateway
from app.domain.integration.contracts import (
    Capability,
    IntegrationRequest,
    MessagingPayload,
)
from pydantic import ValidationError


def mutate_field(target: object, field: str, value: object) -> None:
    setattr(target, field, value)


class TestIntegrationGateway:
    def setup_method(self) -> None:
        self.gateway = IntegrationGateway()

    def test_valid_request_returns_validated(self) -> None:
        payload = MessagingPayload(channel="w", to="1", message="Hi")
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="tenant-1",
            payload=payload,
        )
        validated = self.gateway.validate(request)
        assert validated.request_id == request.request_id
        assert validated.capability == request.capability
        assert validated.tenant_id == request.tenant_id
        assert validated.payload.message == "Hi"

    def test_validated_preserves_metadata(self) -> None:
        payload = MessagingPayload(channel="w", to="1", message="Hi")
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=payload,
            metadata={"source": "webhook"},
        )
        validated = self.gateway.validate(request)
        assert validated.metadata["source"] == "webhook"

    def test_validated_is_different_object(self) -> None:
        payload = MessagingPayload(channel="w", to="1", message="Hi")
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=payload,
        )
        validated = self.gateway.validate(request)
        assert id(validated) != id(request)

    def test_validated_request_is_frozen(self) -> None:
        payload = MessagingPayload(channel="w", to="1", message="Hi")
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=payload,
        )
        validated = self.gateway.validate(request)
        with pytest.raises(ValidationError):
            mutate_field(validated, "tenant_id", "t2")

    def test_http_request_validates_ok(self) -> None:
        payload = MessagingPayload(channel="http", to="", message="")
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.HTTP_REQUEST,
            tenant_id="t1",
            payload=payload,
        )
        validated = self.gateway.validate(request)
        assert validated.capability == Capability.HTTP_REQUEST
