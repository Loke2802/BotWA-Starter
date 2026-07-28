from abc import ABC, abstractmethod

from app.domain.integration.contracts import Capability


class ProviderAdapter(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...


class IntegrationAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[Capability, list[ProviderAdapter]] = {}

    def register(self, capability: Capability, adapter: ProviderAdapter) -> None:
        self._adapters.setdefault(capability, []).append(adapter)

    def resolve(self, capability: Capability) -> list[ProviderAdapter]:
        adapters = self._adapters.get(capability)
        if not adapters:
            raise ValueError(
                f"No adapter registered for capability: '{capability.value}'"
            )
        return adapters
