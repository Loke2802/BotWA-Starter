import pytest
from app.core.integration.provider_registry import (
    IntegrationAdapterRegistry,
    ProviderAdapter,
)
from app.domain.integration.contracts import Capability


class FakeAdapter(ProviderAdapter):
    def __init__(self, provider_id: str, provider_name: str) -> None:
        self._provider_id = provider_id
        self._provider_name = provider_name

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_name(self) -> str:
        return self._provider_name


class TestIntegrationAdapterRegistry:
    def setup_method(self) -> None:
        self.registry = IntegrationAdapterRegistry()
        self.wa_adapter = FakeAdapter("wa-1", "WhatsApp")
        self.http_adapter = FakeAdapter("http-1", "HTTP Generic")

    def test_register_and_resolve_single(self) -> None:
        self.registry.register(Capability.SEND_MESSAGE, self.wa_adapter)
        adapters = self.registry.resolve(Capability.SEND_MESSAGE)
        assert len(adapters) == 1
        assert adapters[0].provider_id == "wa-1"

    def test_register_multiple_for_same_capability(self) -> None:
        self.registry.register(Capability.HTTP_REQUEST, self.http_adapter)
        another = FakeAdapter("http-2", "HTTP Alt")
        self.registry.register(Capability.HTTP_REQUEST, another)
        adapters = self.registry.resolve(Capability.HTTP_REQUEST)
        assert len(adapters) == 2

    def test_resolve_unregistered_raises(self) -> None:
        with pytest.raises(ValueError, match="No adapter registered"):
            self.registry.resolve(Capability.SEND_MESSAGE)

    def test_different_capabilities_isolated(self) -> None:
        self.registry.register(Capability.SEND_MESSAGE, self.wa_adapter)
        with pytest.raises(ValueError, match="No adapter registered"):
            self.registry.resolve(Capability.HTTP_REQUEST)

    def test_provider_adapter_properties(self) -> None:
        assert self.wa_adapter.provider_id == "wa-1"
        assert self.wa_adapter.provider_name == "WhatsApp"
        assert self.http_adapter.provider_id == "http-1"
        assert self.http_adapter.provider_name == "HTTP Generic"

    def test_implements_abc(self) -> None:
        assert issubclass(FakeAdapter, ProviderAdapter)
