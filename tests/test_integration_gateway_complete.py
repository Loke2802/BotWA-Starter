from typing import Any, cast
from unittest.mock import AsyncMock
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
from app.domain.integration.contracts import (
    Capability,
    IntegrationError,
    IntegrationRequest,
    IntegrationResponse,
    IntegrationResult,
    MessagingPayload,
    ProviderContext,
    ValidatedIntegrationRequest,
)


class StubClient(ProviderClient):
    def __init__(self, provider_id: str = "stub", name: str = "Stub") -> None:
        super().__init__(provider_id, name)
        self._execute = AsyncMock(
            return_value=IntegrationResult(
                request_id=uuid4(),
                capability=Capability.SEND_MESSAGE,
                success=True,
                response=IntegrationResponse(success=True, data={"ok": True}),
            )
        )

    async def execute(
        self, context: ProviderContext, request: ValidatedIntegrationRequest[Any]
    ) -> IntegrationResult:
        return cast(IntegrationResult, await self._execute(context, request))


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
def registry() -> IntegrationAdapterRegistry:
    r = IntegrationAdapterRegistry()
    r.register(Capability.SEND_MESSAGE, StubAdapter("wa-1", "WhatsApp"))
    r.register(Capability.HTTP_REQUEST, StubAdapter("http-1", "HTTP"))
    return r


@pytest.fixture
def resolver(registry: IntegrationAdapterRegistry) -> ProviderResolver:
    return ProviderResolver(
        registry=registry,
        configuration_provider=EnvConfigurationProvider(
            base_url="https://api.test.com"
        ),
        credential_provider=EnvCredentialProvider(token="tok"),
    )


@pytest.fixture
def stub_client() -> StubClient:
    return StubClient("wa-1", "WhatsApp")


@pytest.fixture
def gateway(resolver: ProviderResolver, stub_client: StubClient) -> IntegrationGateway:
    return IntegrationGateway(resolver=resolver, clients={"wa-1": stub_client})


def _msg_request() -> IntegrationRequest[MessagingPayload]:
    return IntegrationRequest[MessagingPayload](
        request_id=uuid4(),
        capability=Capability.SEND_MESSAGE,
        tenant_id="tenant-1",
        payload=MessagingPayload(channel="whatsapp", to="5511999999999", message="Hi"),
    )


class TestGatewayOrchestration:
    async def test_execute_success(
        self, gateway: IntegrationGateway, stub_client: StubClient
    ) -> None:
        request = _msg_request()
        result = await gateway.execute(gateway.validate(request))
        assert result.success is True
        assert result.response is not None
        assert result.response.data == {"ok": True}

    async def test_execute_includes_latency(
        self, gateway: IntegrationGateway, stub_client: StubClient
    ) -> None:
        request = _msg_request()
        result = await gateway.execute(gateway.validate(request))
        assert result.latency_ms >= 0
        assert result.attempts == 1

    async def test_resolve_send_message_by_capability(
        self, gateway: IntegrationGateway, stub_client: StubClient
    ) -> None:
        request = _msg_request()
        result = await gateway.execute(gateway.validate(request))
        assert result.success is True

    async def test_execute_fails_for_unregistered_capability(self) -> None:
        empty_registry = IntegrationAdapterRegistry()
        resolver = ProviderResolver(
            registry=empty_registry,
            configuration_provider=EnvConfigurationProvider(),
            credential_provider=EnvCredentialProvider(),
        )
        gw = IntegrationGateway(resolver=resolver, clients={})
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is False
        assert result.error is not None
        assert "No adapter registered" in result.error.message

    async def test_execute_fails_for_missing_client(
        self, resolver: ProviderResolver
    ) -> None:
        gw = IntegrationGateway(resolver=resolver, clients={})
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is False
        assert result.error is not None
        assert "No ProviderClient registered" in result.error.message

    async def test_execute_without_resolver_returns_error(self) -> None:
        gw = IntegrationGateway()
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is False
        assert result.error is not None
        assert "ProviderResolver not configured" in result.error.message


class TestGatewayRetry:
    async def test_retry_on_failure_then_succeeds(
        self, registry: IntegrationAdapterRegistry
    ) -> None:
        resolver = ProviderResolver(
            registry=registry,
            configuration_provider=EnvConfigurationProvider(
                base_url="https://api.test.com"
            ),
            credential_provider=EnvCredentialProvider(token="tok"),
        )
        client = StubClient("wa-1", "WhatsApp")
        fail_results = [
            IntegrationResult(
                request_id=uuid4(),
                capability=Capability.SEND_MESSAGE,
                success=False,
                error=IntegrationError(
                    code="NETWORK_ERROR", message="attempt 1", attempt=1
                ),
            ),
            IntegrationResult(
                request_id=uuid4(),
                capability=Capability.SEND_MESSAGE,
                success=True,
                response=IntegrationResponse(success=True, data={"ok": True}),
            ),
        ]
        client._execute.side_effect = fail_results

        gw = IntegrationGateway(resolver=resolver, clients={"wa-1": client})
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is True
        assert client._execute.call_count == 2

    async def test_retry_exhausted_returns_error(
        self, registry: IntegrationAdapterRegistry
    ) -> None:
        resolver = ProviderResolver(
            registry=registry,
            configuration_provider=EnvConfigurationProvider(
                base_url="https://api.test.com"
            ),
            credential_provider=EnvCredentialProvider(token="tok"),
        )
        client = StubClient("wa-1", "WhatsApp")
        fail_result = IntegrationResult(
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            success=False,
            error=IntegrationError(code="NETWORK_ERROR", message="always fails"),
        )
        client._execute.return_value = fail_result

        gw = IntegrationGateway(resolver=resolver, clients={"wa-1": client})
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is False
        assert client._execute.call_count <= 3

    async def test_non_retryable_error_not_retried(
        self, registry: IntegrationAdapterRegistry
    ) -> None:
        resolver = ProviderResolver(
            registry=registry,
            configuration_provider=EnvConfigurationProvider(
                base_url="https://api.test.com"
            ),
            credential_provider=EnvCredentialProvider(token="tok"),
        )
        client = StubClient("wa-1", "WhatsApp")
        auth_error = IntegrationResult(
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            success=False,
            error=IntegrationError(
                code="AUTH_FAILED",
                message="Invalid credentials",
                details={"status_code": 401},
            ),
        )
        client._execute.return_value = auth_error

        gw = IntegrationGateway(resolver=resolver, clients={"wa-1": client})
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "AUTH_FAILED"
        assert client._execute.call_count == 1

    async def test_timeout_triggers_retry(
        self, registry: IntegrationAdapterRegistry
    ) -> None:
        resolver = ProviderResolver(
            registry=registry,
            configuration_provider=EnvConfigurationProvider(
                base_url="https://api.test.com"
            ),
            credential_provider=EnvCredentialProvider(token="tok"),
        )
        client = StubClient("wa-1", "WhatsApp")
        success_result = IntegrationResult(
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            success=True,
            response=IntegrationResponse(success=True, data={"ok": True}),
        )

        async def slow_then_fast(
            ctx: ProviderContext, req: ValidatedIntegrationRequest[Any]
        ) -> IntegrationResult:
            if client._execute.call_count < 1:
                raise TimeoutError()
            return success_result

        client._execute.side_effect = slow_then_fast

        gw = IntegrationGateway(resolver=resolver, clients={"wa-1": client})
        request = _msg_request()
        result = await gw.execute(gw.validate(request))
        assert result.success is True

    async def test_on_complete_returns_integration_result(
        self, gateway: IntegrationGateway, stub_client: StubClient
    ) -> None:
        request = _msg_request()
        result = await gateway.execute(gateway.validate(request))
        assert isinstance(result, IntegrationResult)
        assert hasattr(result, "success")
        assert hasattr(result, "attempts")
        assert hasattr(result, "latency_ms")


class TestGatewayConstructor:
    def test_default_constructor_still_works(self) -> None:
        gw = IntegrationGateway()
        assert gw._resolver is None
        assert gw._clients == {}

    def test_with_resolver_only(self, resolver: ProviderResolver) -> None:
        gw = IntegrationGateway(resolver=resolver)
        assert gw._resolver is resolver
        assert gw._clients == {}

    def test_with_clients_only(self, stub_client: StubClient) -> None:
        gw = IntegrationGateway(clients={"wa-1": stub_client})
        assert gw._resolver is None
        assert gw._clients["wa-1"] is stub_client
