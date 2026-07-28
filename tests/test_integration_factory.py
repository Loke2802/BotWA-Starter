from app.core.integration.configuration_provider import EnvConfigurationProvider
from app.core.integration.credential_provider import EnvCredentialProvider
from app.core.integration.factory import (
    create_default_registry,
    create_integration_service,
    create_provider_clients,
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
from app.core.integration.service import IntegrationService
from app.domain.integration.contracts import Capability


class TestFactory:
    def test_create_default_registry_contains_whatsapp(self) -> None:
        registry = create_default_registry()
        adapters = registry.resolve(Capability.SEND_MESSAGE)
        assert len(adapters) == 1
        assert adapters[0].provider_id == "whatsapp"

    def test_create_default_registry_contains_http(self) -> None:
        registry = create_default_registry()
        adapters = registry.resolve(Capability.HTTP_REQUEST)
        assert len(adapters) == 1
        assert adapters[0].provider_id == "http_default"

    def test_create_provider_clients_contains_all(self) -> None:
        clients = create_provider_clients()
        assert "whatsapp" in clients
        assert "http_default" in clients
        assert "sms_stub" in clients
        assert "email_stub" in clients

    def test_provider_clients_are_correct_types(self) -> None:
        clients = create_provider_clients()
        assert isinstance(clients["whatsapp"], WhatsAppProviderClient)
        assert isinstance(clients["http_default"], HttpProviderClient)
        assert isinstance(clients["sms_stub"], SmsProviderClient)
        assert isinstance(clients["email_stub"], EmailProviderClient)

    def test_create_integration_service_with_defaults(self) -> None:
        service, gateway, monitor, health_checker = create_integration_service()
        assert isinstance(service, IntegrationService)
        assert isinstance(gateway, IntegrationGateway)
        assert isinstance(monitor, IntegrationMonitor)
        assert isinstance(health_checker, HealthChecker)
        assert hasattr(service, "execute")

    def test_create_integration_service_custom_providers(self) -> None:
        config_provider = EnvConfigurationProvider(base_url="https://custom.api.com")
        cred_provider = EnvCredentialProvider(token="custom-token")
        service, *_ = create_integration_service(
            configuration_provider=config_provider,
            credential_provider=cred_provider,
        )
        assert isinstance(service, IntegrationService)

    def test_create_integration_service_custom_clients(self) -> None:
        clients: dict[str, ProviderClient] = {
            "whatsapp": WhatsAppProviderClient("wa-custom", "WhatsApp Custom")
        }
        service, *_ = create_integration_service(clients=clients)
        assert isinstance(service, IntegrationService)

    def test_create_integration_service_wires_gateway(self) -> None:
        service, gateway, *_ = create_integration_service()
        assert service._gateway is gateway

    def test_registry_and_clients_match(self) -> None:
        registry = create_default_registry()
        clients = create_provider_clients()
        wa = registry.resolve(Capability.SEND_MESSAGE)[0]
        assert wa.provider_id in clients
        http = registry.resolve(Capability.HTTP_REQUEST)[0]
        assert http.provider_id in clients
