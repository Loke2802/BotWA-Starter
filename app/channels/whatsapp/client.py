from typing import cast

from httpx import AsyncClient, Timeout

from app.infrastructure.settings import Settings

MESSAGES_URL = "https://graph.facebook.com/{api_version}/{phone_number_id}/messages"


class WhatsAppClient:
    def __init__(
        self, settings: Settings, http_client: AsyncClient | None = None
    ) -> None:
        self._access_token = settings.whatsapp_access_token
        self._phone_number_id = settings.whatsapp_phone_number_id
        self._api_version = settings.whatsapp_api_version
        self._base_url = MESSAGES_URL.format(
            api_version=self._api_version,
            phone_number_id=self._phone_number_id,
        )
        self._http_client = http_client

    async def send_message(self, payload: dict[str, object]) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        if self._http_client is not None:
            response = await self._http_client.post(
                self._base_url, headers=headers, json=payload
            )
            response.raise_for_status()
            return cast("dict[str, object]", response.json())
        async with AsyncClient(timeout=Timeout(30.0)) as client:
            response = await client.post(self._base_url, headers=headers, json=payload)
            response.raise_for_status()
            return cast("dict[str, object]", response.json())
