import base64
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from app.application.whatsapp_live.client import WhatsAppCloudApiError
from app.application.whatsapp_live.sender import (
    WhatsAppChannelDeliveryError,
    WhatsAppChannelMessageSender,
)
from app.domain.channel.contracts import (
    OutboundChannelMessage,
    ResolvedChannelContext,
)
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    InMemoryWhatsAppConfigurationRepository,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.infrastructure.whatsapp.meta_client import MetaWhatsAppCloudApiClient
from app.security.secret_cipher import EnvironmentSecretCipher


def cipher() -> EnvironmentSecretCipher:
    key = base64.urlsafe_b64encode(b"l" * 32).decode("ascii")
    return EnvironmentSecretCipher(key)


def configuration(
    secret_cipher: EnvironmentSecretCipher,
    *,
    status: str = "active",
    access_token: bool = True,
) -> WhatsAppChannelConfigurationModel:
    now = datetime.now(UTC)
    return WhatsAppChannelConfigurationModel(
        id=uuid4(),
        organization_id=uuid4(),
        bot_id=uuid4(),
        display_name="Support",
        phone_number_id="123456789",
        whatsapp_business_account_id="waba-1",
        public_webhook_id=uuid4(),
        status=status,
        webhook_enabled=True,
        verify_token_ciphertext=secret_cipher.encrypt("verify-token"),
        access_token_ciphertext=(
            secret_cipher.encrypt("access-token") if access_token else None
        ),
        app_secret_ciphertext=secret_cipher.encrypt("app-secret"),
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def resolved(
    model: WhatsAppChannelConfigurationModel,
) -> ResolvedChannelContext:
    return ResolvedChannelContext(
        channel_type="whatsapp",
        organization_id=model.organization_id,
        bot_id=model.bot_id,
        channel_configuration_id=model.id,
        external_channel_id=model.phone_number_id,
    )


def outbound(text: str = "Respuesta") -> OutboundChannelMessage:
    return OutboundChannelMessage(
        channel_type="whatsapp",
        external_recipient_id="51999999999",
        text=text,
        reply_to_external_message_id="wamid.1",
    )


async def test_meta_client_builds_safe_versioned_request() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.content
        return httpx.Response(
            200,
            json={"messages": [{"id": "wamid.provider"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = MetaWhatsAppCloudApiClient(
            api_version="v22.0",
            timeout_seconds=5,
            http_client=http,
        )
        result = await client.send_text_message(
            phone_number_id="123456789",
            access_token="secret-token",
            recipient_id="51999999999",
            text="Hola",
            reply_to_message_id="wamid.1",
        )

    assert result.provider_message_id == "wamid.provider"
    assert captured["url"] == ("https://graph.facebook.com/v22.0/123456789/messages")
    assert captured["authorization"] == "Bearer secret-token"
    captured_body = captured["body"]
    assert isinstance(captured_body, bytes)
    assert b'"message_id":"wamid.1"' in captured_body


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (400, "INVALID_REQUEST", False),
        (401, "AUTHENTICATION_FAILED", False),
        (429, "RATE_LIMITED", True),
        (500, "PROVIDER_UNAVAILABLE", True),
    ],
)
async def test_meta_client_classifies_http_failures(
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request, text="sensitive")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = MetaWhatsAppCloudApiClient(
            api_version="v22.0",
            timeout_seconds=5,
            http_client=http,
        )
        with pytest.raises(WhatsAppCloudApiError) as caught:
            await client.send_text_message(
                phone_number_id="123456789",
                access_token="secret-token",
                recipient_id="51999999999",
                text="Hola",
            )

    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert "sensitive" not in str(caught.value)
    assert "secret-token" not in repr(caught.value)


async def test_meta_client_classifies_timeout_without_leaking_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = MetaWhatsAppCloudApiClient(
            api_version="v22.0",
            timeout_seconds=5,
            http_client=http,
        )
        with pytest.raises(WhatsAppCloudApiError) as caught:
            await client.send_text_message(
                phone_number_id="123456789",
                access_token="secret-token",
                recipient_id="51999999999",
                text="private body",
            )

    assert caught.value.code == "TIMEOUT"
    assert caught.value.retryable
    assert "sensitive timeout" not in str(caught.value)


async def test_fake_client_supports_controlled_outcomes_and_safe_calls() -> None:
    client = FakeWhatsAppCloudApiClient(("timeout", "success"))

    with pytest.raises(WhatsAppCloudApiError) as caught:
        await client.send_text_message(
            phone_number_id="123456789",
            access_token="secret-token",
            recipient_id="51999999999",
            text="contenido sensible",
        )
    result = await client.send_text_message(
        phone_number_id="123456789",
        access_token="secret-token",
        recipient_id="51999999999",
        text="contenido sensible",
    )

    assert caught.value.retryable
    assert result.provider_message_id.startswith("fake-")
    assert client.calls[0] == {
        "phone_number_hash": client.calls[0]["phone_number_hash"],
        "recipient_hash": client.calls[0]["recipient_hash"],
        "text_length": 18,
        "reply_configured": False,
        "token_configured": True,
    }
    assert "secret-token" not in repr(client.calls)
    assert "contenido sensible" not in repr(client.calls)
    assert "51999999999" not in repr(client.calls)


async def test_sender_loads_scoped_active_configuration_and_decrypts_in_memory() -> (
    None
):
    secret_cipher = cipher()
    model = configuration(secret_cipher)
    repository = InMemoryWhatsAppConfigurationRepository()
    repository.add(model)
    client = FakeWhatsAppCloudApiClient()
    sender = WhatsAppChannelMessageSender(
        repository,
        secret_cipher,
        client,
        max_text_chars=4096,
    )

    result = await sender.send(outbound(), resolved(model))

    assert result.status == "sent"
    assert len(client.calls) == 1
    assert model.access_token_ciphertext != "access-token"


@pytest.mark.parametrize(
    ("status", "access_token", "recipient", "text", "code"),
    [
        ("inactive", True, "51999999999", "Hola", "CHANNEL_UNAVAILABLE"),
        ("active", False, "51999999999", "Hola", "ACCESS_TOKEN_MISSING"),
        ("active", True, "invalid", "Hola", "INVALID_RECIPIENT"),
        ("active", True, "51999999999", "Texto largo", "MESSAGE_TOO_LONG"),
    ],
)
async def test_sender_rejects_invalid_delivery_conditions(
    status: str,
    access_token: bool,
    recipient: str,
    text: str,
    code: str,
) -> None:
    secret_cipher = cipher()
    model = configuration(
        secret_cipher,
        status=status,
        access_token=access_token,
    )
    repository = InMemoryWhatsAppConfigurationRepository()
    repository.add(model)
    sender = WhatsAppChannelMessageSender(
        repository,
        secret_cipher,
        FakeWhatsAppCloudApiClient(),
        max_text_chars=4 if code == "MESSAGE_TOO_LONG" else 4096,
    )
    message = outbound(text).model_copy(
        update={"external_recipient_id": recipient},
    )

    with pytest.raises(WhatsAppChannelDeliveryError) as caught:
        await sender.send(message, resolved(model))

    assert caught.value.code == code
