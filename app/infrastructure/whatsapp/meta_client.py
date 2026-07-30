import re
from typing import cast

import httpx

from app.application.whatsapp_live.client import (
    WhatsAppCloudApiClient,
    WhatsAppCloudApiError,
)
from app.domain.whatsapp_live.contracts import WhatsAppSendResponse

_API_VERSION = re.compile(r"v\d+\.\d+")
_PHONE_NUMBER_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
_BASE_URL = "https://graph.facebook.com/{api_version}/{phone_number_id}/messages"


class MetaWhatsAppCloudApiClient(WhatsAppCloudApiClient):
    def __init__(
        self,
        *,
        api_version: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if _API_VERSION.fullmatch(api_version) is None:
            raise ValueError("invalid Meta API version")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_version = api_version
        self._timeout = httpx.Timeout(timeout_seconds)
        self._http_client = http_client

    async def send_text_message(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> WhatsAppSendResponse:
        if _PHONE_NUMBER_ID.fullmatch(phone_number_id) is None:
            raise WhatsAppCloudApiError("INVALID_PHONE_NUMBER_ID", retryable=False)
        if not access_token:
            raise WhatsAppCloudApiError("ACCESS_TOKEN_MISSING", retryable=False)
        payload: dict[str, object] = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": text},
        }
        if reply_to_message_id is not None:
            payload["context"] = {"message_id": reply_to_message_id}
        url = _BASE_URL.format(
            api_version=self._api_version,
            phone_number_id=phone_number_id,
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        url,
                        headers=headers,
                        json=payload,
                    )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise WhatsAppCloudApiError("TIMEOUT", retryable=True) from exc
        except httpx.RequestError as exc:
            raise WhatsAppCloudApiError("NETWORK_ERROR", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                code, retryable = "RATE_LIMITED", True
            elif status_code >= 500:
                code, retryable = "PROVIDER_UNAVAILABLE", True
            elif status_code in {401, 403}:
                code, retryable = "AUTHENTICATION_FAILED", False
            else:
                code, retryable = "INVALID_REQUEST", False
            raise WhatsAppCloudApiError(code, retryable=retryable) from exc

        try:
            data = cast("dict[str, object]", response.json())
            messages = data.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError
            first = messages[0]
            if not isinstance(first, dict):
                raise ValueError
            provider_message_id = first.get("id")
            if not isinstance(provider_message_id, str) or not provider_message_id:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise WhatsAppCloudApiError(
                "INVALID_PROVIDER_RESPONSE",
                retryable=False,
            ) from exc
        return WhatsAppSendResponse(provider_message_id=provider_message_id)
