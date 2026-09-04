from app.application.whatsapp_live.client import (
    WhatsAppCloudApiClient,
    WhatsAppCloudApiError,
)
from app.domain.whatsapp_live.contracts import WhatsAppSendResponse


class DisabledWhatsAppCloudApiClient(WhatsAppCloudApiClient):
    """Fails closed if an outbound send reaches a disabled runtime."""

    async def send_text_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> WhatsAppSendResponse:
        del (
            phone_number_id,
            access_token,
            recipient_id,
            text,
            reply_to_message_id,
        )
        raise WhatsAppCloudApiError("OUTBOUND_DISABLED", retryable=False)
