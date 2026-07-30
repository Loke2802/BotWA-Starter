from collections.abc import Generator

from fastapi import HTTPException, status

from app.application.whatsapp_configuration.resolver import (
    WhatsAppChannelResolver,
)
from app.application.whatsapp_configuration.service import (
    WhatsAppConfigurationService,
)
from app.application.whatsapp_configuration.signature import (
    WhatsAppWebhookSignatureVerifier,
)
from app.application.whatsapp_configuration.webhook import (
    WhatsAppWebhookValidationService,
)
from app.infrastructure.database import get_session
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    SqlAlchemyWhatsAppConfigurationRepository,
)
from app.infrastructure.settings import get_settings
from app.security.secret_cipher import (
    EnvironmentSecretCipher,
    SecretCipher,
    SecretCipherConfigurationError,
)


def get_whatsapp_secret_cipher() -> SecretCipher:
    try:
        return EnvironmentSecretCipher.from_settings(get_settings())
    except SecretCipherConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp secret encryption is unavailable",
        ) from exc


def get_whatsapp_configuration_service() -> Generator[WhatsAppConfigurationService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield WhatsAppConfigurationService(
            repository=SqlAlchemyWhatsAppConfigurationRepository(session),
            bot_repository=BotRepository(session),
            organization_repository=OrganizationRepository(session),
            secret_cipher=get_whatsapp_secret_cipher(),
            session=session,
        )
    finally:
        session_generator.close()


def get_whatsapp_channel_resolver() -> Generator[WhatsAppChannelResolver]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield WhatsAppChannelResolver(
            SqlAlchemyWhatsAppConfigurationRepository(session),
        )
    finally:
        session_generator.close()


def get_whatsapp_webhook_validation_service() -> (
    Generator[WhatsAppWebhookValidationService]
):
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield WhatsAppWebhookValidationService(
            repository=SqlAlchemyWhatsAppConfigurationRepository(session),
            secret_cipher=get_whatsapp_secret_cipher(),
            signature_verifier=WhatsAppWebhookSignatureVerifier(),
        )
    finally:
        session_generator.close()
