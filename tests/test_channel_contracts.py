from pathlib import Path
from uuid import uuid4

import pytest
from app.domain.channel.contracts import ChannelIdentity, ResolvedChannelContext
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationCreate,
    WhatsAppChannelConfigurationUpdate,
    WhatsAppSecretRotation,
)
from pydantic import ValidationError


def test_generic_channel_contracts_are_explicit_and_immutable() -> None:
    organization_id = uuid4()
    bot_id = uuid4()
    configuration_id = uuid4()

    identity = ChannelIdentity(
        channel_type="whatsapp",
        external_channel_id=" phone-123 ",
    )
    context = ResolvedChannelContext(
        channel_type="whatsapp",
        organization_id=organization_id,
        bot_id=bot_id,
        channel_configuration_id=configuration_id,
        external_channel_id="phone-123",
    )

    assert identity.external_channel_id == "phone-123"
    assert context.organization_id == organization_id
    with pytest.raises(ValidationError):
        ChannelIdentity.model_validate(
            {"channel_type": "telegram", "external_channel_id": "123"},
        )
    with pytest.raises(ValidationError):
        context.organization_id = uuid4()  # type: ignore[misc]


def test_whatsapp_contracts_reject_secret_and_state_leaks() -> None:
    request = WhatsAppChannelConfigurationCreate(
        display_name=" Support ",
        phone_number_id=" phone-123 ",
        whatsapp_business_account_id=" waba-123 ",
    )

    assert request.display_name == "Support"
    assert request.phone_number_id == "phone-123"
    assert request.whatsapp_business_account_id == "waba-123"
    with pytest.raises(ValidationError):
        WhatsAppChannelConfigurationUpdate.model_validate({"status": "active"})
    with pytest.raises(ValidationError):
        WhatsAppChannelConfigurationUpdate.model_validate(
            {"verify_token": "not-allowed"},
        )
    with pytest.raises(ValidationError):
        WhatsAppSecretRotation()
    with pytest.raises(ValidationError):
        WhatsAppSecretRotation(verify_token=None)


def test_core_engines_do_not_import_whatsapp_product_modules() -> None:
    forbidden_imports = (
        "app.channels.whatsapp",
        "app.application.whatsapp_configuration",
        "app.domain.whatsapp_configuration",
    )

    for path in Path("app/core").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(module in source for module in forbidden_imports), path
