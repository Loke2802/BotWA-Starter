from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from app.core.integration.provider_client import (
    EmailProviderClient,
    HttpProviderClient,
    ProviderClient,
    SmsProviderClient,
    WhatsAppProviderClient,
)
from app.domain.integration.contracts import (
    AuthCredential,
    Capability,
    IntegrationConfiguration,
    MessagingPayload,
    Provider,
    ProviderContext,
    ProviderStatus,
    ValidatedIntegrationRequest,
)
from httpx import HTTPStatusError, RequestError


def _make_context(
    base_url: str = "https://api.example.com",
    token: str = "test-token",
    timeout: int = 30,
) -> ProviderContext:
    provider = Provider(
        provider_id="http_default",
        name="HTTP",
        capability=Capability.HTTP_REQUEST,
        status=ProviderStatus.ACTIVE,
    )
    config = IntegrationConfiguration(
        provider_id="http_default",
        tenant_id="tenant-1",
        base_url=base_url,
        timeout_seconds=timeout,
    )
    creds = AuthCredential(value=token)
    return ProviderContext(
        provider=provider, base_url=base_url, credentials=creds, config=config
    )


def _make_request(
    payload: object,
    capability: Capability = Capability.HTTP_REQUEST,
) -> ValidatedIntegrationRequest[object]:
    return ValidatedIntegrationRequest[object](
        request_id=uuid4(),
        capability=capability,
        tenant_id="tenant-1",
        payload=payload,
    )


def _mock_response(
    status_code: int = 200,
    json_data: dict[str, object] | None = None,
    text: str = "",
    raise_error: HTTPStatusError | None = None,
) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.text = text or (json_data if json_data else "")
    resp.json.return_value = json_data or {}
    if raise_error:
        resp.raise_for_status.side_effect = raise_error
    else:
        resp.raise_for_status.return_value = None
    return resp


def _mock_async_client(mock_response: Mock) -> tuple[AsyncMock, Mock]:
    client_instance = AsyncMock()
    client_instance.__aenter__.return_value = client_instance
    return client_instance, mock_response


class TestProviderClient:
    def test_abc_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            ProviderClient("p1", "Test")  # type: ignore[abstract]

    def test_http_client_defaults(self) -> None:
        client = HttpProviderClient()
        assert client.provider_id == "http_default"
        assert client.provider_name == "HTTP"

    def test_whatsapp_client_defaults(self) -> None:
        client = WhatsAppProviderClient()
        assert client.provider_id == "whatsapp"
        assert client.provider_name == "WhatsApp"

    def test_sms_client_defaults(self) -> None:
        client = SmsProviderClient()
        assert client.provider_id == "sms_stub"
        assert client.provider_name == "SMS"

    def test_email_client_defaults(self) -> None:
        client = EmailProviderClient()
        assert client.provider_id == "email_stub"
        assert client.provider_name == "Email"

    def test_custom_provider_id(self) -> None:
        client = HttpProviderClient(provider_id="my-http", provider_name="My HTTP")
        assert client.provider_id == "my-http"
        assert client.provider_name == "My HTTP"

    def test_provider_client_is_adapter_subclass(self) -> None:
        from app.core.integration.provider_registry import ProviderAdapter

        assert issubclass(ProviderClient, ProviderAdapter)


class TestSmsStub:
    async def test_returns_not_implemented(self) -> None:
        client = SmsProviderClient()
        context = _make_context()
        request = _make_request({"to": "123", "message": "Hi"})
        result = await client.execute(context, request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "NOT_IMPLEMENTED"


class TestEmailStub:
    async def test_returns_not_implemented(self) -> None:
        client = EmailProviderClient()
        context = _make_context()
        request = _make_request({"to": "a@b.com", "subject": "Hi"})
        result = await client.execute(context, request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "NOT_IMPLEMENTED"


class TestHttpProviderClient:
    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_successful_get_request(self, mock_async_client_cls: Any) -> None:
        resp = _mock_response(
            status_code=200,
            json_data={"result": "ok"},
            text='{"result": "ok"}',
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.request = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = HttpProviderClient()
        context = _make_context(base_url="https://api.test.com")
        request = _make_request({"method": "GET", "path": "/v1/resource"})

        result = await client.execute(context, request)
        assert result.success is True
        assert result.response is not None
        assert result.response.data == {"result": "ok"}

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_successful_post_with_body(self, mock_async_client_cls: Any) -> None:
        resp = _mock_response(
            status_code=201,
            json_data={"id": "new-123"},
            text='{"id": "new-123"}',
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.request = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = HttpProviderClient()
        context = _make_context(base_url="https://api.test.com")
        request = _make_request(
            {
                "method": "POST",
                "path": "/v1/items",
                "body": {"name": "test"},
            }
        )

        result = await client.execute(context, request)
        assert result.success is True
        assert result.response is not None
        assert result.response.data is not None
        assert result.response.data["id"] == "new-123"

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_http_4xx_error(self, mock_async_client_cls: Any) -> None:
        resp = _mock_response(
            status_code=404,
            text='{"error": "not found"}',
            raise_error=HTTPStatusError(
                "404 Not Found",
                request=Mock(),
                response=Mock(status_code=404, text='{"error": "not found"}'),
            ),
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.request = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = HttpProviderClient()
        context = _make_context()
        request = _make_request({"method": "GET", "path": "/missing"})

        result = await client.execute(context, request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "HTTP_ERROR"

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_network_error(self, mock_async_client_cls: Any) -> None:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.request = AsyncMock(
            side_effect=RequestError("Connection refused")
        )
        mock_async_client_cls.return_value = mock_instance

        client = HttpProviderClient()
        context = _make_context()
        request = _make_request({"method": "GET", "path": "/test"})

        result = await client.execute(context, request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "NETWORK_ERROR"

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_includes_auth_header(self, mock_async_client_cls: Any) -> None:
        resp = _mock_response(status_code=200, json_data={}, text="{}")
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.request = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = HttpProviderClient()
        context = _make_context(token="my-secret-token")
        request = _make_request({"method": "GET", "path": "/secure"})

        await client.execute(context, request)

        call_kwargs = mock_instance.request.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret-token"

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_missing_method_defaults_to_get(
        self, mock_async_client_cls: Any
    ) -> None:
        resp = _mock_response(status_code=200, json_data={}, text="{}")
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.request = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = HttpProviderClient()
        context = _make_context()
        request = _make_request({})

        await client.execute(context, request)

        call_args = mock_instance.request.call_args
        assert call_args.kwargs["method"] == "GET"


class TestWhatsAppProviderClient:
    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_successful_text_message(self, mock_async_client_cls: Any) -> None:
        resp = _mock_response(
            status_code=200,
            json_data={"messages": [{"id": "wamid.ABC123"}]},
            text='{"messages": [{"id": "wamid.ABC123"}]}',
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = WhatsAppProviderClient()
        provider = Provider(
            provider_id="whatsapp",
            name="WhatsApp",
            capability=Capability.SEND_MESSAGE,
        )
        config = IntegrationConfiguration(
            provider_id="whatsapp",
            tenant_id="t1",
            base_url="https://graph.facebook.com/v22.0/123456/messages",
        )
        creds = AuthCredential(value="wa-token")
        context = ProviderContext(
            provider=provider,
            base_url="https://graph.facebook.com/v22.0/123456/messages",
            credentials=creds,
            config=config,
        )
        request = ValidatedIntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message="Hello!"
            ),
        )

        result = await client.execute(context, request)

        assert result.success is True
        assert result.response is not None
        assert result.response.data is not None

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_payload_as_dict(self, mock_async_client_cls: Any) -> None:
        resp = _mock_response(status_code=200, json_data={}, text="{}")
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = WhatsAppProviderClient()
        provider = Provider(
            provider_id="whatsapp",
            name="WhatsApp",
            capability=Capability.SEND_MESSAGE,
        )
        config = IntegrationConfiguration(
            provider_id="whatsapp",
            tenant_id="t1",
            base_url="https://graph.facebook.com/v22.0/123/messages",
        )
        creds = AuthCredential(value="tok")
        context = ProviderContext(
            provider=provider,
            base_url="https://graph.facebook.com/v22.0/123/messages",
            credentials=creds,
            config=config,
        )
        request: ValidatedIntegrationRequest[dict[str, str]] = (
            ValidatedIntegrationRequest(
                request_id=uuid4(),
                capability=Capability.SEND_MESSAGE,
                tenant_id="t1",
                payload={
                    "to": "5511999999999",
                    "message": "Hi!",
                    "channel": "whatsapp",
                },
            )
        )

        result = await client.execute(context, request)
        assert result.success is True

    @patch("app.core.integration.provider_client.AsyncClient")
    async def test_api_error_returns_error_result(
        self, mock_async_client_cls: Any
    ) -> None:
        resp = _mock_response(
            status_code=401,
            text='{"error": {"message": "Invalid token"}}',
            raise_error=HTTPStatusError(
                "401 Unauthorized",
                request=Mock(),
                response=Mock(
                    status_code=401,
                    text='{"error": {"message": "Invalid token"}}',
                ),
            ),
        )
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post = AsyncMock(return_value=resp)
        mock_async_client_cls.return_value = mock_instance

        client = WhatsAppProviderClient()
        provider = Provider(
            provider_id="whatsapp",
            name="WhatsApp",
            capability=Capability.SEND_MESSAGE,
        )
        config = IntegrationConfiguration(
            provider_id="whatsapp",
            tenant_id="t1",
            base_url="https://graph.facebook.com/messages",
        )
        context = ProviderContext(
            provider=provider,
            base_url="https://graph.facebook.com/messages",
            config=config,
        )
        request = ValidatedIntegrationRequest[MessagingPayload](
            request_id=uuid4(),
            capability=Capability.SEND_MESSAGE,
            tenant_id="t1",
            payload=MessagingPayload(
                channel="whatsapp", to="5511999999999", message="Hi"
            ),
        )

        result = await client.execute(context, request)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "WHATSAPP_API_ERROR"
