from uuid import uuid4

import pytest
from app.core.integration.configuration_provider import (
    EnvConfigurationProvider,
)
from app.core.integration.credential_provider import (
    EnvCredentialProvider,
)
from app.core.integration.provider_registry import (
    IntegrationAdapterRegistry,
    ProviderAdapter,
)
from app.core.integration.provider_resolver import ProviderResolver
from app.domain.integration.contracts import (
    Capability,
    MessagingPayload,
    ValidatedIntegrationRequest,
)
from pydantic import ValidationError


def mutate_field(target: object, field: str, value: object) -> None:
    setattr(target, field, value)


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


class TestProviderResolver:
    def setup_method(self) -> None:
        self.registry = IntegrationAdapterRegistry()
        self.registry.register(Capability.SEND_MESSAGE, StubAdapter("wa-1", "WhatsApp"))
        self.registry.register(
            Capability.HTTP_REQUEST, StubAdapter("http-1", "HTTP Generic")
        )
        self.config_provider = EnvConfigurationProvider(
            base_url="https://graph.facebook.com"
        )
        self.credential_provider = EnvCredentialProvider(token="test-token-123")
        self.resolver = ProviderResolver(
            registry=self.registry,
            configuration_provider=self.config_provider,
            credential_provider=self.credential_provider,
        )

    def _make_validated_request(
        self, capability: Capability
    ) -> ValidatedIntegrationRequest[MessagingPayload]:
        return ValidatedIntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=capability,
            tenant_id="tenant-1",
            payload=MessagingPayload(channel="w", to="1", message="Hi"),
        )

    def test_resolve_send_message(self) -> None:
        request = self._make_validated_request(Capability.SEND_MESSAGE)
        ctx = self.resolver.resolve(request)
        assert ctx.provider.provider_id == "wa-1"
        assert ctx.provider.capability == Capability.SEND_MESSAGE
        assert ctx.base_url == "https://graph.facebook.com"

    def test_resolve_http_request(self) -> None:
        request = self._make_validated_request(Capability.HTTP_REQUEST)
        ctx = self.resolver.resolve(request)
        assert ctx.provider.provider_id == "http-1"
        assert ctx.provider.capability == Capability.HTTP_REQUEST

    def test_resolve_includes_credentials(self) -> None:
        request = self._make_validated_request(Capability.SEND_MESSAGE)
        ctx = self.resolver.resolve(request)
        assert ctx.credentials is not None
        assert ctx.credentials.value == "test-token-123"

    def test_resolve_includes_config(self) -> None:
        request = self._make_validated_request(Capability.SEND_MESSAGE)
        ctx = self.resolver.resolve(request)
        assert ctx.config is not None
        assert ctx.config.provider_id == "wa-1"

    def test_resolve_sets_provider_version(self) -> None:
        request = self._make_validated_request(Capability.SEND_MESSAGE)
        ctx = self.resolver.resolve(request)
        assert ctx.provider.version == "1.0"

    def test_resolve_fails_for_unregistered_capability(self) -> None:
        request = self._make_validated_request(Capability.SEND_MESSAGE)
        self.registry = IntegrationAdapterRegistry()
        empty_resolver = ProviderResolver(
            registry=self.registry,
            configuration_provider=self.config_provider,
            credential_provider=self.credential_provider,
        )
        with pytest.raises(ValueError, match="No adapter registered"):
            empty_resolver.resolve(request)

    def test_resolved_context_is_frozen(self) -> None:
        request = self._make_validated_request(Capability.SEND_MESSAGE)
        ctx = self.resolver.resolve(request)
        with pytest.raises(ValidationError):
            mutate_field(ctx, "base_url", "changed")
