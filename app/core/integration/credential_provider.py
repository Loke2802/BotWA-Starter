from abc import ABC, abstractmethod

from app.domain.integration.contracts import AuthCredential


class CredentialProvider(ABC):
    @abstractmethod
    def get_credentials(self, tenant_id: str, provider_id: str) -> AuthCredential: ...


class EnvCredentialProvider(CredentialProvider):
    def __init__(self, token: str = "", token_type: str = "bearer_token") -> None:
        self._token = token
        self._token_type = token_type

    def get_credentials(self, tenant_id: str, provider_id: str) -> AuthCredential:
        return AuthCredential(type=self._token_type, value=self._token)
