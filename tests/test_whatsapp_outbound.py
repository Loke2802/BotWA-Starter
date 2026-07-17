from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from app.channels.whatsapp.client import WhatsAppClient
from app.channels.whatsapp.mapper import to_whatsapp_text_payload
from app.channels.whatsapp.sender import WhatsAppSender
from app.domain.conversation.contracts import ChannelResponse
from app.infrastructure.settings import Settings


def make_settings(
    whatsapp_access_token: str = "test_token",
    whatsapp_phone_number_id: str = "123456789",
    whatsapp_api_version: str = "v22.0",
) -> Settings:
    return Settings(
        whatsapp_access_token=whatsapp_access_token,
        whatsapp_phone_number_id=whatsapp_phone_number_id,
        whatsapp_api_version=whatsapp_api_version,
    )


def make_response_mock(
    status_code: int = 200, json_data: dict[str, object] | None = None
) -> MagicMock:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data or {}
    return mock_response


class TestMapper:
    def test_to_whatsapp_text_payload(self) -> None:
        response = ChannelResponse(status="accepted", message="Hola, ¿cómo estás?")
        payload = to_whatsapp_text_payload(response, to="15557654321")

        assert payload == {
            "messaging_product": "whatsapp",
            "to": "15557654321",
            "type": "text",
            "text": {"body": "Hola, ¿cómo estás?"},
        }


class TestClient:
    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(json_data={"message_id": "wamid.abc"})
        mock_client.post = AsyncMock(return_value=mock_response)

        client = WhatsAppClient(settings, http_client=mock_client)
        result = await client.send_message(
            {"messaging_product": "whatsapp", "to": "15557654321", "type": "text"}
        )

        assert result == {"message_id": "wamid.abc"}
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_http_error(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(status_code=400)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request",
            request=httpx.Request("POST", "https://example.com"),
            response=mock_response,
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        client = WhatsAppClient(settings, http_client=mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            await client.send_message(
                {
                    "messaging_product": "whatsapp",
                    "to": "15557654321",
                    "type": "text",
                }
            )

    @pytest.mark.asyncio
    async def test_send_message_auth_error(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(status_code=401)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=httpx.Request("POST", "https://example.com"),
            response=mock_response,
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        client = WhatsAppClient(settings, http_client=mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            await client.send_message(
                {
                    "messaging_product": "whatsapp",
                    "to": "15557654321",
                    "type": "text",
                }
            )

    @pytest.mark.asyncio
    async def test_send_message_timeout(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError(
                "Timeout", request=httpx.Request("POST", "https://example.com")
            )
        )

        client = WhatsAppClient(settings, http_client=mock_client)

        with pytest.raises(httpx.RequestError):
            await client.send_message(
                {
                    "messaging_product": "whatsapp",
                    "to": "15557654321",
                    "type": "text",
                }
            )


class TestSender:
    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(json_data={"message_id": "wamid.abc"})
        mock_client.post = AsyncMock(return_value=mock_response)

        wa_client = WhatsAppClient(settings, http_client=mock_client)
        sender = WhatsAppSender(wa_client)

        result = await sender.send(
            ChannelResponse(status="accepted", message="Hola"), to="15557654321"
        )

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_send_http_error_does_not_crash(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(status_code=500)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "https://example.com"),
            response=mock_response,
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        wa_client = WhatsAppClient(settings, http_client=mock_client)
        sender = WhatsAppSender(wa_client)

        result = await sender.send(
            ChannelResponse(status="accepted", message="Hola"), to="15557654321"
        )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_auth_error_does_not_crash(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(status_code=401)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=httpx.Request("POST", "https://example.com"),
            response=mock_response,
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        wa_client = WhatsAppClient(settings, http_client=mock_client)
        sender = WhatsAppSender(wa_client)

        result = await sender.send(
            ChannelResponse(status="accepted", message="Hola"), to="15557654321"
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_timeout_does_not_crash(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError(
                "Timeout", request=httpx.Request("POST", "https://example.com")
            )
        )

        wa_client = WhatsAppClient(settings, http_client=mock_client)
        sender = WhatsAppSender(wa_client)

        result = await sender.send(
            ChannelResponse(status="accepted", message="Hola"), to="15557654321"
        )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_integration_with_client(self) -> None:
        settings = make_settings()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = make_response_mock(json_data={"message_id": "wamid.abc"})
        mock_client.post = AsyncMock(return_value=mock_response)

        wa_client = WhatsAppClient(settings, http_client=mock_client)
        sender = WhatsAppSender(wa_client)

        result = await sender.send(
            ChannelResponse(status="accepted", message="Hello"), to="15557654321"
        )

        assert result.success is True
        call_args = mock_client.post.call_args[1]
        assert call_args["json"] == {
            "messaging_product": "whatsapp",
            "to": "15557654321",
            "type": "text",
            "text": {"body": "Hello"},
        }
        assert call_args["headers"]["Authorization"] == "Bearer test_token"
