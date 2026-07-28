import pytest
from app.core.integration.configuration_provider import (
    ConfigurationProvider,
    EnvConfigurationProvider,
)
from app.domain.integration.contracts import IntegrationConfiguration
from pydantic import ValidationError


def mutate_field(target: object, field: str, value: object) -> None:
    setattr(target, field, value)


class TestConfigurationProvider:
    def test_interface_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            ConfigurationProvider()  # type: ignore[abstract]

    def test_env_provider_default_base_url(self) -> None:
        provider = EnvConfigurationProvider()
        config = provider.get_config("tenant-1", "wa-1")
        assert isinstance(config, IntegrationConfiguration)
        assert config.provider_id == "wa-1"
        assert config.tenant_id == "tenant-1"
        assert config.base_url == ""

    def test_env_provider_custom_base_url(self) -> None:
        provider = EnvConfigurationProvider(base_url="https://api.example.com")
        config = provider.get_config("t1", "p1")
        assert config.base_url == "https://api.example.com"

    def test_env_provider_sensible_defaults(self) -> None:
        provider = EnvConfigurationProvider()
        config = provider.get_config("t1", "p1")
        assert config.timeout_seconds == 30
        assert config.retry_max_attempts == 3
        assert config.rate_limit_max_per_second == 80

    def test_frozen_config(self) -> None:
        provider = EnvConfigurationProvider()
        config = provider.get_config("t1", "p1")
        with pytest.raises(ValidationError):
            mutate_field(config, "base_url", "changed")
