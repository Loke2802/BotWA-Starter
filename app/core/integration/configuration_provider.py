from abc import ABC, abstractmethod

from app.domain.integration.contracts import IntegrationConfiguration


class ConfigurationProvider(ABC):
    @abstractmethod
    def get_config(
        self, tenant_id: str, provider_id: str
    ) -> IntegrationConfiguration: ...


class EnvConfigurationProvider(ConfigurationProvider):
    def __init__(self, base_url: str = "") -> None:
        self._base_url = base_url

    def get_config(self, tenant_id: str, provider_id: str) -> IntegrationConfiguration:
        return IntegrationConfiguration(
            provider_id=provider_id,
            tenant_id=tenant_id,
            base_url=self._base_url,
        )
