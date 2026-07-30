from abc import ABC, abstractmethod

from app.domain.whatsapp_live.contracts import WhatsAppSendResponse


class WhatsAppCloudApiError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable

    def __repr__(self) -> str:
        return (
            "WhatsAppCloudApiError("
            f"code={self.code!r}, retryable={self.retryable!r})"
        )


class WhatsAppCloudApiClient(ABC):
    @abstractmethod
    async def send_text_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> WhatsAppSendResponse: ...
