from typing import Any
from uuid import uuid4

import pytest
from app.core.integration.configuration_provider import EnvConfigurationProvider
from app.core.integration.credential_provider import EnvCredentialProvider
from app.core.integration.gateway import IntegrationGateway
from app.core.integration.provider_client import ProviderClient
from app.core.integration.provider_registry import (
    IntegrationAdapterRegistry,
    ProviderAdapter,
)
from app.core.integration.provider_resolver import ProviderResolver
from app.core.integration.service import IntegrationService
from app.domain.integration.contracts import (
    Capability,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationResult,
    MessagingPayload,
    ProviderContext,
    ValidatedIntegrationRequest,
)


class StubClient(ProviderClient):
    def __init__(self, provider_id: str = "stub") -> None:
        super().__init__(provider_id, "Stub")

    async def execute(
        self, context: ProviderContext, request: ValidatedIntegrationRequest[Any]
    ) -> IntegrationResult:
        return IntegrationResult(
            request_id=request.request_id,
            capability=request.capability,
            success=True,
            response=IntegrationResponse(success=True, data={"ok": True}),
        )


class StubAdapter(ProviderAdapter):
    def __init__(self, provider_id: str, provider_name: str) -> None:
        self._provider_id = provider_id
        self._provider_name = provider_name

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_name(self) -> str:
        return self._provider_name


@pytest.fixture
def service() -> IntegrationService:
    registry = IntegrationAdapterRegistry()
    registry.register(Capability.SEND_MESSAGE, StubAdapter("wa-1", "WhatsApp"))
    resolver = ProviderResolver(
        registry=registry,
        configuration_provider=EnvConfigurationProvider(
            base_url="https://api.test.com"
        ),
        credential_provider=EnvCredentialProvider(token="tok"),
    )
    gateway = IntegrationGateway(
        resolver=resolver,
        clients={"wa-1": StubClient("wa-1")},
    )
    return IntegrationService(gateway=gateway)


class TestIntegrationService:
    async def test_execute_returns_integration_result(
        self, service: IntegrationService
    ) -> None:
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="tenant-1",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message="Hi"
            ),
        )
        result = await service.execute(request)
        assert isinstance(result, IntegrationResult)
        assert result.success is True
        assert result.response is not None
        assert result.response.data == {"ok": True}

    async def test_execute_validates_request(self, service: IntegrationService) -> None:
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="tenant-1",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message="Hi"
            ),
        )
        result = await service.execute(request)
        assert result.success is True

    async def test_execute_propagates_gateway_error(
        self, service: IntegrationService
    ) -> None:
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message=""
            ),
        )
        result = await service.execute(request)
        assert result.success is False

    async def test_execute_never_raises_exception(
        self, service: IntegrationService
    ) -> None:
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="tenant-1",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message="Hi"
            ),
        )
        result = await service.execute(request)
        assert result.success is True

    async def test_execute_handles_invalid_request_gracefully(
        self, service: IntegrationService
    ) -> None:
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message=""
            ),
        )
        result = await service.execute(request)
        assert result.success is False
        assert result.error is not None

    async def test_http_request_capability(self, service: IntegrationService) -> None:
        request = IntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.HTTP_REQUEST,
            tenant_id="tenant-1",
            payload=MessagingPayload(channel="http", to="", message=""),
        )
        result = await service.execute(request)
        assert isinstance(result, IntegrationResult)

    async def test_service_is_single_public_api(self) -> None:
        service = IntegrationService(gateway=IntegrationGateway())
        assert hasattr(service, "execute")

    async def test_http_request_with_dict_payload(self) -> None:
        registry = IntegrationAdapterRegistry()
        registry.register(Capability.HTTP_REQUEST, StubAdapter("http-1", "HTTP"))
        resolver = ProviderResolver(
            registry=registry,
            configuration_provider=EnvConfigurationProvider(
                base_url="https://api.test.com"
            ),
            credential_provider=EnvCredentialProvider(token="tok"),
        )
        client = StubClient("http-1")
        gateway = IntegrationGateway(resolver=resolver, clients={"http-1": client})
        svc = IntegrationService(gateway=gateway)

        request: IntegrationRequest[dict[str, object]] = IntegrationRequest[
            dict[str, object]
        ](
            request_id=uuid4(),
            capability=Capability.HTTP_REQUEST,
            tenant_id="t1",
            payload={"method": "GET", "path": "/api/data"},
        )
        result = await svc.execute(request)
        assert result.success is True
