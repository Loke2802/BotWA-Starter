from app.application.integration_management.providers import (
    CalendarIntegrationAdapter,
)


class IntegrationProviderNotSupportedError(LookupError):
    pass


class IntegrationProviderRegistry:
    def __init__(self, adapters: tuple[CalendarIntegrationAdapter, ...]) -> None:
        self._adapters = {adapter.provider: adapter for adapter in adapters}

    def calendar(self, provider: str) -> CalendarIntegrationAdapter:
        adapter = self._adapters.get(provider)
        if adapter is None:
            raise IntegrationProviderNotSupportedError(
                "integration provider unavailable"
            )
        return adapter
