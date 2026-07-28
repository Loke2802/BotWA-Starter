import pytest
from app.core.integration.credential_provider import (
    CredentialProvider,
    EnvCredentialProvider,
)
from app.domain.integration.contracts import AuthCredential
from pydantic import ValidationError


def mutate_field(target: object, field: str, value: object) -> None:
    setattr(target, field, value)


class TestCredentialProvider:
    def test_interface_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            CredentialProvider()  # type: ignore[abstract]

    def test_env_provider_default_type(self) -> None:
        provider = EnvCredentialProvider(token="my-token")
        creds = provider.get_credentials("tenant-1", "wa-1")
        assert isinstance(creds, AuthCredential)
        assert creds.value == "my-token"
        assert creds.type == "bearer_token"

    def test_env_provider_custom_type(self) -> None:
        provider = EnvCredentialProvider(token="key-abc", token_type="api_key")
        creds = provider.get_credentials("t1", "p1")
        assert creds.type == "api_key"
        assert creds.value == "key-abc"

    def test_env_provider_empty_token(self) -> None:
        provider = EnvCredentialProvider()
        creds = provider.get_credentials("t1", "p1")
        assert creds.value == ""

    def test_frozen_credential(self) -> None:
        provider = EnvCredentialProvider(token="t")
        creds = provider.get_credentials("t1", "p1")
        with pytest.raises(ValidationError):
            mutate_field(creds, "value", "changed")
