from collections.abc import Generator

from app.application.integration_management.oauth_state import OAuthStateSigner
from app.application.integration_management.service import IntegrationManagementService
from app.infrastructure.database import get_session
from app.infrastructure.integrations.google_calendar import GoogleCalendarAdapter
from app.infrastructure.integrations.registry import IntegrationProviderRegistry
from app.infrastructure.repositories.integration_management_repository import (
    IntegrationManagementRepository,
)
from app.infrastructure.settings import Settings, get_settings
from app.security.secret_cipher import EnvironmentSecretCipher, SecretCipher


class IntegrationSettingsSecretCipher(SecretCipher):
    """Resolve the existing Fernet infrastructure only when a secret is needed."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def encrypt(self, value: str) -> str:
        return EnvironmentSecretCipher.from_integration_settings(
            self._settings
        ).encrypt(value)

    def decrypt(self, value: str) -> str:
        return EnvironmentSecretCipher.from_integration_settings(
            self._settings
        ).decrypt(value)


def get_integration_management_service() -> Generator[IntegrationManagementService]:
    settings = get_settings()
    session_generator = get_session()
    session = next(session_generator)
    try:
        adapter = GoogleCalendarAdapter(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
            timeout_seconds=settings.google_calendar_timeout_seconds,
        )
        yield IntegrationManagementService(
            IntegrationManagementRepository(session),
            session,
            IntegrationSettingsSecretCipher(settings),
            OAuthStateSigner(
                secret_key=(
                    settings.integration_oauth_state_secret or settings.auth_secret_key
                ),
                algorithm=settings.auth_algorithm,
                ttl_seconds=settings.integration_oauth_state_ttl_seconds,
            ),
            IntegrationProviderRegistry((adapter,)),
        )
    finally:
        session_generator.close()
