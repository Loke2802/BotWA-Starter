import hmac
from uuid import UUID

from app.application.whatsapp_configuration.repository import (
    WhatsAppConfigurationRepository,
)
from app.application.whatsapp_configuration.signature import (
    WhatsAppWebhookSignatureVerifier,
)
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.security.secret_cipher import SecretCipher, SecretCipherError


class WhatsAppWebhookValidationError(ValueError):
    pass


class WhatsAppWebhookValidationService:
    def __init__(
        self,
        repository: WhatsAppConfigurationRepository,
        secret_cipher: SecretCipher,
        signature_verifier: WhatsAppWebhookSignatureVerifier,
    ) -> None:
        self._repository = repository
        self._secret_cipher = secret_cipher
        self._signature_verifier = signature_verifier

    def verify_challenge(
        self,
        public_webhook_id: UUID,
        *,
        mode: str | None,
        verify_token: str | None,
        challenge: str | None,
    ) -> str:
        if mode != "subscribe" or verify_token is None or challenge is None:
            raise WhatsAppWebhookValidationError("webhook verification failed")
        configuration = self._get_active_configuration(public_webhook_id)
        expected_token = self._decrypt_required(
            configuration.verify_token_ciphertext,
        )
        if not hmac.compare_digest(expected_token, verify_token):
            raise WhatsAppWebhookValidationError("webhook verification failed")
        return challenge

    def verify_signature(
        self,
        public_webhook_id: UUID,
        *,
        raw_body: bytes,
        signature_header: str | None,
    ) -> None:
        configuration = self._get_active_configuration(public_webhook_id)
        app_secret = self._decrypt_required(configuration.app_secret_ciphertext)
        if not self._signature_verifier.verify(
            raw_body,
            signature_header,
            app_secret,
        ):
            raise WhatsAppWebhookValidationError("webhook signature is invalid")

    def _get_active_configuration(
        self,
        public_webhook_id: UUID,
    ) -> WhatsAppChannelConfigurationModel:
        try:
            configuration = self._repository.get_active_by_public_webhook_id(
                public_webhook_id,
            )
        except ValueError as exc:
            raise WhatsAppWebhookValidationError(
                "webhook configuration is ambiguous",
            ) from exc
        if configuration is None:
            raise WhatsAppWebhookValidationError(
                "webhook configuration was not resolved",
            )
        return configuration

    def _decrypt_required(self, ciphertext: str | None) -> str:
        if ciphertext is None:
            raise WhatsAppWebhookValidationError(
                "webhook secret is not configured",
            )
        try:
            return self._secret_cipher.decrypt(ciphertext)
        except SecretCipherError as exc:
            raise WhatsAppWebhookValidationError(
                "webhook secret is unavailable",
            ) from exc
