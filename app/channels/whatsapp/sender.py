import structlog
from httpx import HTTPStatusError, RequestError

from app.channels.whatsapp.client import WhatsAppClient
from app.channels.whatsapp.mapper import to_whatsapp_text_payload
from app.domain.conversation.contracts import ChannelResponse

logger = structlog.get_logger(__name__)


class SendResult:
    def __init__(self, success: bool, error: str | None = None) -> None:
        self.success = success
        self.error = error


class WhatsAppSender:
    def __init__(self, client: WhatsAppClient) -> None:
        self._client = client

    async def send(self, response: ChannelResponse, to: str) -> SendResult:
        payload = to_whatsapp_text_payload(response, to)
        try:
            await self._client.send_message(payload)
            return SendResult(success=True)
        except HTTPStatusError as exc:
            logger.error(
                "whatsapp_api_error",
                status_code=exc.response.status_code,
            )
            return SendResult(
                success=False,
                error=f"HTTP {exc.response.status_code}",
            )
        except RequestError:
            logger.error("whatsapp_request_error", error_code="PROVIDER_UNAVAILABLE")
            return SendResult(success=False, error="provider unavailable")
