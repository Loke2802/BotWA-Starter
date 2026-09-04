import base64
import hashlib
import hmac
import json
from collections.abc import Generator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.api.whatsapp_configuration_dependencies import (
    get_whatsapp_webhook_validation_service,
)
from app.api.whatsapp_live_dependencies import (
    get_whatsapp_cloud_api_client,
    get_whatsapp_live_message_processor,
)
from app.application.whatsapp_configuration.signature import (
    WhatsAppWebhookSignatureVerifier,
)
from app.application.whatsapp_configuration.webhook import (
    WhatsAppWebhookValidationService,
)
from app.application.whatsapp_live.processor import (
    WhatsAppLiveMessageProcessor,
    WhatsAppRuntimeRoutingError,
)
from app.domain.whatsapp_live.contracts import WhatsAppParsedWebhook
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    InMemoryWhatsAppConfigurationRepository,
)
from app.infrastructure.settings import Settings, get_settings
from app.infrastructure.whatsapp.disabled_client import DisabledWhatsAppCloudApiClient
from app.main import create_app
from app.security.secret_cipher import EnvironmentSecretCipher
from fastapi.testclient import TestClient


class RecordingProcessor:
    def __init__(self) -> None:
        self.calls: list[tuple[WhatsAppParsedWebhook, UUID, UUID]] = []
        self.fail_routing = False

    async def process(
        self,
        payload: WhatsAppParsedWebhook,
        *,
        public_webhook_id: UUID,
        correlation_id: UUID,
    ) -> tuple[object, ...]:
        if self.fail_routing:
            raise WhatsAppRuntimeRoutingError("controlled")
        self.calls.append((payload, public_webhook_id, correlation_id))
        return ()


def body() -> bytes:
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": "123456789"},
                                "messages": [
                                    {
                                        "from": "51999999999",
                                        "id": "wamid.1",
                                        "timestamp": "1785384000",
                                        "type": "text",
                                        "text": {"body": "texto privado"},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def signature(raw_body: bytes, secret: str = "app-secret") -> str:
    return (
        "sha256="
        + hmac.new(
            secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
    )


async def test_disabled_client_mode_allows_inbound_dependency_construction() -> None:
    client = get_whatsapp_cloud_api_client(
        Settings(whatsapp_live_client_mode="disabled"),
    )

    assert isinstance(client, DisabledWhatsAppCloudApiClient)


@pytest.fixture
def endpoint_runtime() -> Generator[tuple[TestClient, UUID, RecordingProcessor],]:
    key = base64.urlsafe_b64encode(b"e" * 32).decode("ascii")
    cipher = EnvironmentSecretCipher(key)
    repository = InMemoryWhatsAppConfigurationRepository()
    now = datetime.now(UTC)
    configuration = WhatsAppChannelConfigurationModel(
        id=uuid4(),
        organization_id=uuid4(),
        bot_id=uuid4(),
        display_name="Endpoint",
        phone_number_id="123456789",
        whatsapp_business_account_id="waba-endpoint",
        public_webhook_id=uuid4(),
        status="active",
        webhook_enabled=True,
        verify_token_ciphertext=cipher.encrypt("verify-token"),
        access_token_ciphertext=cipher.encrypt("access-token"),
        app_secret_ciphertext=cipher.encrypt("app-secret"),
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    repository.add(configuration)
    validator = WhatsAppWebhookValidationService(
        repository,
        cipher,
        WhatsAppWebhookSignatureVerifier(),
    )
    processor = RecordingProcessor()
    settings = Settings(
        use_database=False,
        whatsapp_live_client_mode="fake",
        whatsapp_webhook_max_body_bytes=1024,
        whatsapp_webhook_max_events=10,
    )
    app = create_app()
    app.dependency_overrides[get_whatsapp_webhook_validation_service] = (
        lambda: validator
    )
    app.dependency_overrides[get_whatsapp_live_message_processor] = lambda: cast(
        "WhatsAppLiveMessageProcessor",
        processor,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, configuration.public_webhook_id, processor
    app.dependency_overrides.clear()


def test_post_webhook_validates_signature_before_mapping(
    endpoint_runtime: tuple[TestClient, UUID, RecordingProcessor],
) -> None:
    client, webhook_id, processor = endpoint_runtime
    raw = body()

    invalid = client.post(
        f"/webhooks/whatsapp/{webhook_id}",
        content=b"not-json",
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )
    valid = client.post(
        f"/webhooks/whatsapp/{webhook_id}",
        content=raw,
        headers={"X-Hub-Signature-256": signature(raw)},
    )

    assert invalid.status_code == 403
    assert valid.status_code == 200
    assert valid.text == "OK"
    assert len(processor.calls) == 1
    assert processor.calls[0][0].messages[0].text == "texto privado"


def test_post_webhook_rejects_missing_signature(
    endpoint_runtime: tuple[TestClient, UUID, RecordingProcessor],
) -> None:
    client, webhook_id, processor = endpoint_runtime

    response = client.post(
        f"/webhooks/whatsapp/{webhook_id}",
        content=body(),
    )

    assert response.status_code == 403
    assert processor.calls == []


def test_post_webhook_rejects_malformed_and_oversized_payload(
    endpoint_runtime: tuple[TestClient, UUID, RecordingProcessor],
) -> None:
    client, webhook_id, processor = endpoint_runtime
    malformed = b"not-json"

    invalid = client.post(
        f"/webhooks/whatsapp/{webhook_id}",
        content=malformed,
        headers={"X-Hub-Signature-256": signature(malformed)},
    )
    oversized = b"x" * 1025
    too_large = client.post(
        f"/webhooks/whatsapp/{webhook_id}",
        content=oversized,
        headers={"X-Hub-Signature-256": signature(oversized)},
    )

    assert invalid.status_code == 400
    assert too_large.status_code == 413
    assert processor.calls == []


def test_post_webhook_returns_controlled_error_for_routing_mismatch(
    endpoint_runtime: tuple[TestClient, UUID, RecordingProcessor],
) -> None:
    client, webhook_id, processor = endpoint_runtime
    processor.fail_routing = True
    raw = body()

    response = client.post(
        f"/webhooks/whatsapp/{webhook_id}",
        content=raw,
        headers={"X-Hub-Signature-256": signature(raw)},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "webhook channel was not resolved"}
