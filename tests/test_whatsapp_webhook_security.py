import base64
import hashlib
import hmac
import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.application.whatsapp_configuration.signature import (
    WhatsAppWebhookSignatureVerifier,
)
from app.application.whatsapp_configuration.webhook import (
    WhatsAppWebhookValidationError,
    WhatsAppWebhookValidationService,
)
from app.infrastructure.logging import SensitiveQueryParameterFilter
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.whatsapp_configuration_repository import (
    InMemoryWhatsAppConfigurationRepository,
)
from app.security.secret_cipher import EnvironmentSecretCipher


def cipher() -> EnvironmentSecretCipher:
    key = base64.urlsafe_b64encode(b"s" * 32).decode("ascii")
    return EnvironmentSecretCipher(key)


def active_configuration(
    secret_cipher: EnvironmentSecretCipher,
) -> WhatsAppChannelConfigurationModel:
    now = datetime.now(UTC)
    return WhatsAppChannelConfigurationModel(
        id=uuid4(),
        organization_id=uuid4(),
        bot_id=uuid4(),
        display_name="Support",
        phone_number_id="phone-1",
        whatsapp_business_account_id="waba-1",
        public_webhook_id=uuid4(),
        status="active",
        webhook_enabled=True,
        verify_token_ciphertext=secret_cipher.encrypt("verify-token"),
        app_secret_ciphertext=secret_cipher.encrypt("app-secret"),
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_webhook_challenge_uses_encrypted_token_and_constant_comparison() -> None:
    secret_cipher = cipher()
    repository = InMemoryWhatsAppConfigurationRepository()
    configuration = active_configuration(secret_cipher)
    repository.add(configuration)
    service = WhatsAppWebhookValidationService(
        repository,
        secret_cipher,
        WhatsAppWebhookSignatureVerifier(),
    )

    assert (
        service.verify_challenge(
            configuration.public_webhook_id,
            mode="subscribe",
            verify_token="verify-token",
            challenge="12345",
        )
        == "12345"
    )
    with pytest.raises(WhatsAppWebhookValidationError):
        service.verify_challenge(
            configuration.public_webhook_id,
            mode="subscribe",
            verify_token="wrong",
            challenge="12345",
        )


def test_hmac_signature_accepts_only_exact_sha256_digest() -> None:
    verifier = WhatsAppWebhookSignatureVerifier()
    body = b'{"event":"test"}'
    signature = (
        "sha256="
        + hmac.new(
            b"app-secret",
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    assert verifier.verify(body, signature, "app-secret")
    assert not verifier.verify(body, None, "app-secret")
    assert not verifier.verify(body, "sha1=invalid", "app-secret")
    assert not verifier.verify(body, f"{signature}0", "app-secret")
    assert not verifier.verify(body + b"x", signature, "app-secret")


def test_access_log_redacts_webhook_verify_token() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1",
            "GET",
            "/webhooks/whatsapp/id?hub.mode=subscribe"
            "&hub.verify_token=secret-token&hub.challenge=123",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert SensitiveQueryParameterFilter().filter(record)
    assert "secret-token" not in record.getMessage()
    assert "hub.verify_token=%5BREDACTED%5D" in record.getMessage()
    assert "hub.challenge=123" in record.getMessage()
