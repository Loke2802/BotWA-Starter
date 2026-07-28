from app.core.integration.circuit_breaker import CircuitBreaker
from app.core.integration.configuration_provider import (
    ConfigurationProvider,
    EnvConfigurationProvider,
)
from app.core.integration.credential_provider import (
    CredentialProvider,
    EnvCredentialProvider,
)
from app.core.integration.gateway import IntegrationGateway
from app.core.integration.health_checker import HealthChecker
from app.core.integration.monitor import IntegrationMonitor
from app.core.integration.provider_client import (
    EmailProviderClient,
    HttpProviderClient,
    ProviderClient,
    SmsProviderClient,
    WhatsAppProviderClient,
)
from app.core.integration.provider_registry import IntegrationAdapterRegistry
from app.core.integration.provider_resolver import ProviderResolver
from app.core.integration.rate_limiter import RateLimiter
from app.core.integration.service import IntegrationService
from app.domain.integration.contracts import (
    Capability,
    IntegrationConfiguration,
)


def create_default_registry() -> IntegrationAdapterRegistry:
    registry = IntegrationAdapterRegistry()
    registry.register(Capability.SEND_MESSAGE, WhatsAppProviderClient())
    registry.register(Capability.HTTP_REQUEST, HttpProviderClient())
    return registry


def create_provider_clients() -> dict[str, ProviderClient]:
    clients: dict[str, ProviderClient] = {}
    for obj in (
        WhatsAppProviderClient(),
        HttpProviderClient(),
        SmsProviderClient(),
        EmailProviderClient(),
    ):
        clients[obj.provider_id] = obj
    return clients


def create_circuit_breakers(
    providers: list[IntegrationConfiguration] | None = None,
) -> dict[str, CircuitBreaker]:
    cbs: dict[str, CircuitBreaker] = {}
    if providers:
        for cfg in providers:
            cbs[cfg.provider_id] = CircuitBreaker(
                failure_threshold=cfg.circuit_breaker_failure_threshold,
                recovery_timeout=cfg.circuit_breaker_recovery_timeout,
            )
    return cbs


def create_integration_service(
    registry: IntegrationAdapterRegistry | None = None,
    configuration_provider: ConfigurationProvider | None = None,
    credential_provider: CredentialProvider | None = None,
    clients: dict[str, ProviderClient] | None = None,
    monitor: IntegrationMonitor | None = None,
) -> tuple[IntegrationService, IntegrationGateway, IntegrationMonitor, HealthChecker]:
    if registry is None:
        registry = create_default_registry()
    if configuration_provider is None:
        configuration_provider = EnvConfigurationProvider()
    if credential_provider is None:
        credential_provider = EnvCredentialProvider()
    if clients is None:
        clients = create_provider_clients()
    if monitor is None:
        monitor = IntegrationMonitor()

    resolver = ProviderResolver(
        registry=registry,
        configuration_provider=configuration_provider,
        credential_provider=credential_provider,
    )
    rate_limiter = RateLimiter()
    gateway = IntegrationGateway(
        resolver=resolver,
        clients=clients,
        rate_limiter=rate_limiter,
        monitor=monitor,
    )
    health_checker = HealthChecker(
        registry=registry,
        clients=clients,
        monitor=monitor,
    )
    service = IntegrationService(gateway=gateway)
    return service, gateway, monitor, health_checker
