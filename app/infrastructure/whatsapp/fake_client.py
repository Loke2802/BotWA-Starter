import hashlib
from collections import deque
from collections.abc import Iterable

from app.application.whatsapp_live.client import (
    WhatsAppCloudApiClient,
    WhatsAppCloudApiError,
)
from app.domain.whatsapp_live.contracts import WhatsAppSendResponse

_OUTCOMES = frozenset({"success", "timeout", "429", "400", "401", "500"})


class FakeWhatsAppCloudApiClient(WhatsAppCloudApiClient):
    def __init__(self, outcomes: Iterable[str] = ("success",)) -> None:
        normalized = tuple(outcomes)
        if not normalized or any(outcome not in _OUTCOMES for outcome in normalized):
            raise ValueError("invalid fake WhatsApp client outcome")
        self._outcomes = deque(normalized)
        self.calls: list[dict[str, object]] = []

    async def send_text_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> WhatsAppSendResponse:
        self.calls.append(
            {
                "phone_number_hash": _hash(phone_number_id),
                "recipient_hash": _hash(recipient_id),
                "text_length": len(text),
                "reply_configured": reply_to_message_id is not None,
                "token_configured": bool(access_token),
            }
        )
        outcome = self._outcomes[0]
        if len(self._outcomes) > 1:
            self._outcomes.popleft()
        if outcome == "timeout":
            raise WhatsAppCloudApiError("TIMEOUT", retryable=True)
        if outcome == "429":
            raise WhatsAppCloudApiError("RATE_LIMITED", retryable=True)
        if outcome == "500":
            raise WhatsAppCloudApiError("PROVIDER_UNAVAILABLE", retryable=True)
        if outcome == "401":
            raise WhatsAppCloudApiError("AUTHENTICATION_FAILED", retryable=False)
        if outcome == "400":
            raise WhatsAppCloudApiError("INVALID_REQUEST", retryable=False)

        digest = hashlib.sha256(
            (
                f"{phone_number_id}:{recipient_id}:{text}:"
                f"{reply_to_message_id or ''}"
            ).encode()
        ).hexdigest()[:24]
        return WhatsAppSendResponse(provider_message_id=f"fake-{digest}")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
