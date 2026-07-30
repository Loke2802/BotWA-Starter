import re

from app.application.channel.messaging import ChannelMessageSender
from app.application.whatsapp_configuration.repository import (
    WhatsAppConfigurationRepository,
)
from app.application.whatsapp_live.client import WhatsAppCloudApiClient
from app.domain.channel.contracts import (
    ChannelDeliveryResult,
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.security.secret_cipher import SecretCipher, SecretCipherError

_RECIPIENT = re.compile(r"[1-9]\d{5,19}")


class WhatsAppChannelDeliveryError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class WhatsAppChannelMessageSender(ChannelMessageSender):
    def __init__(
        self,
        configuration_repository: WhatsAppConfigurationRepository,
        secret_cipher: SecretCipher,
        client: WhatsAppCloudApiClient,
        *,
        max_text_chars: int,
    ) -> None:
        self._configuration_repository = configuration_repository
        self._secret_cipher = secret_cipher
        self._client = client
        self._max_text_chars = max_text_chars

    async def send(
        self,
        message: OutboundChannelMessage,
        context: ResolvedChannelContext,
    ) -> ChannelDeliveryResult:
        if message.channel_type != "whatsapp" or context.channel_type != "whatsapp":
            raise WhatsAppChannelDeliveryError("CHANNEL_MISMATCH")
        if len(message.text) > self._max_text_chars:
            raise WhatsAppChannelDeliveryError("MESSAGE_TOO_LONG")
        if _RECIPIENT.fullmatch(message.external_recipient_id) is None:
            raise WhatsAppChannelDeliveryError("INVALID_RECIPIENT")

        configuration = self._configuration_repository.get_scoped(
            context.channel_configuration_id,
            context.organization_id,
            context.bot_id,
        )
        if (
            configuration is None
            or configuration.status != "active"
            or not configuration.webhook_enabled
            or configuration.phone_number_id != context.external_channel_id
        ):
            raise WhatsAppChannelDeliveryError("CHANNEL_UNAVAILABLE")
        if configuration.access_token_ciphertext is None:
            raise WhatsAppChannelDeliveryError("ACCESS_TOKEN_MISSING")
        try:
            access_token = self._secret_cipher.decrypt(
                configuration.access_token_ciphertext,
            )
        except SecretCipherError as exc:
            raise WhatsAppChannelDeliveryError("ACCESS_TOKEN_UNAVAILABLE") from exc

        try:
            result = await self._client.send_text_message(
                phone_number_id=configuration.phone_number_id,
                access_token=access_token,
                recipient_id=message.external_recipient_id,
                text=message.text,
                reply_to_message_id=message.reply_to_external_message_id,
            )
        except Exception as exc:
            from app.application.whatsapp_live.client import WhatsAppCloudApiError

            if isinstance(exc, WhatsAppCloudApiError):
                raise WhatsAppChannelDeliveryError(
                    exc.code,
                    retryable=exc.retryable,
                ) from exc
            raise
        return ChannelDeliveryResult(
            provider_message_id=result.provider_message_id,
        )
