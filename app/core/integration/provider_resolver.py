from typing import Any

from app.core.integration.configuration_provider import ConfigurationProvider
from app.core.integration.credential_provider import CredentialProvider
from app.core.integration.provider_registry import IntegrationAdapterRegistry
from app.domain.integration.contracts import (
    Provider,
    ProviderContext,
    ProviderStatus,
    ValidatedIntegrationRequest,
)


class ProviderResolver:
    def __init__(
        self,
        registry: IntegrationAdapterRegistry,
        configuration_provider: ConfigurationProvider,
        credential_provider: CredentialProvider,
    ) -> None:
        self._registry = registry
        self._config_provider = configuration_provider
        self._credential_provider = credential_provider

    def resolve(self, request: ValidatedIntegrationRequest[Any]) -> ProviderContext:
        adapters = self._registry.resolve(request.capability)
        first = adapters[0]

        config = self._config_provider.get_config(request.tenant_id, first.provider_id)
        credentials = self._credential_provider.get_credentials(
            request.tenant_id, first.provider_id
        )

        provider = Provider(
            provider_id=first.provider_id,
            name=first.provider_name,
            capability=request.capability,
            status=ProviderStatus.ACTIVE,
            version=config.api_version or "1.0",
        )

        resolved = ProviderContext(
            provider=provider,
            base_url=config.base_url,
            credentials=credentials,
            config=config,
        )
        return resolved
