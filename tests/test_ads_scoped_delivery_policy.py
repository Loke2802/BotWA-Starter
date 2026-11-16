"""Ads transport permission must remain scoped and off by default."""

import hashlib
from uuid import uuid4

import pytest
from app.application.whatsapp_live.recipient_policy import ad_recipient_allowed
from app.domain.channel.contracts import ResolvedChannelContext
from app.domain.generative_ai.contracts import AIConfig
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations.ai_consumer import dispatch_one
from sqlalchemy import select

from tests.test_generative_ai import Runtime, runtime
from tests.test_whatsapp_ads_only import configure, inbound

__all__ = ["runtime"]


def scope(runtime: Runtime) -> ResolvedChannelContext:
    return ResolvedChannelContext(
        channel_type="whatsapp",
        organization_id=runtime.channel.organization_id,
        bot_id=runtime.channel.bot_id,
        channel_configuration_id=runtime.channel.id,
        external_channel_id=runtime.channel.phone_number_id,
    )


def restricted_meta_settings(runtime: Runtime) -> None:
    runtime.settings = runtime.settings.model_copy(
        update={
            "whatsapp_live_client_mode": "meta",
            "whatsapp_outbound_restrict_recipients": True,
            "whatsapp_outbound_allowed_recipients": (),
        }
    )
    runtime.service.settings = runtime.settings


async def test_ad_reply_uses_scoped_permission_without_opening_global_transport(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    restricted_meta_settings(runtime)
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "ad-scoped", "12345")
    assert await runtime.service.run_once()
    client = FakeWhatsAppCloudApiClient()
    monkeypatch.setattr(
        "app.operations.ai_consumer.get_whatsapp_cloud_api_client", lambda _: client
    )
    assert await dispatch_one(runtime.service)
    assert not await dispatch_one(runtime.service)
    assert len(client.calls) == 1
    assert (
        client.calls[0]["recipient_hash"]
        == hashlib.sha256(b"51999999999").hexdigest()[:12]
    )
    assert runtime.settings.whatsapp_outbound_restrict_recipients
    assert runtime.settings.whatsapp_outbound_allowed_recipients == ()


@pytest.mark.parametrize(
    "deny",
    [
        "flag_off",
        "pilot_denied",
        "no_origin",
        "wrong_origin_line",
        "other_recipient",
        "other_tenant",
        "other_bot",
        "other_line",
        "wrong_external_line",
        "channel_inactive",
        "webhook_off",
        "ai_disabled",
        "scope_removed",
        "bot_inactive",
        "org_inactive",
    ],
)
async def test_scoped_ads_permission_cannot_open_unrelated_recipients(
    runtime: Runtime, deny: str
) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "origin", "12345")
    restricted_meta_settings(runtime)
    with runtime.sessions() as session:
        context = scope(runtime)
        recipient = "51999999999"
        assert ad_recipient_allowed(session, runtime.settings, recipient, context)
        bot = session.get(BotModel, runtime.channel.bot_id)
        conversation = session.scalars(select(ConversationModel)).one()
        channel = session.get(WhatsAppChannelConfigurationModel, runtime.channel.id)
        assert bot and channel
        if deny in {"flag_off", "pilot_denied", "ai_disabled"}:
            config = AIConfig.model_validate(bot.settings["generative_ai"]).model_dump()
            if deny == "flag_off":
                config["whatsapp_ads_only"] = False
            elif deny == "pilot_denied":
                config["pilot_recipients"] = []
            else:
                config["enabled"] = False
            bot.settings = {**bot.settings, "generative_ai": config}
        elif deny == "no_origin":
            conversation.extra_data = {}
        elif deny == "wrong_origin_line":
            conversation.extra_data = {
                "whatsapp_ad_origin": {
                    "source_id": "12345",
                    "configuration_id": str(uuid4()),
                }
            }
        elif deny == "other_recipient":
            recipient = "51977777777"
        elif deny in {"other_tenant", "other_bot", "other_line"}:
            key = {
                "other_tenant": "organization_id",
                "other_bot": "bot_id",
                "other_line": "channel_configuration_id",
            }[deny]
            context = context.model_copy(update={key: uuid4()})
        elif deny == "wrong_external_line":
            context = context.model_copy(
                update={"external_channel_id": "unrelated-line"}
            )
        elif deny == "channel_inactive":
            channel.status = "inactive"
        elif deny == "webhook_off":
            channel.webhook_enabled = False
        elif deny == "scope_removed":
            runtime.settings = runtime.settings.model_copy(
                update={"ai_pilot_scopes": ()}
            )
        elif deny == "bot_inactive":
            bot.status = "inactive"
        elif deny == "org_inactive":
            org = session.get(OrganizationModel, runtime.channel.organization_id)
            assert org
            org.status = "inactive"
        session.commit()
        assert not ad_recipient_allowed(session, runtime.settings, recipient, context)


async def test_policy_revocation_blocks_a_ready_ad_reply(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "ready-ad", "12345")
    assert await runtime.service.run_once()
    restricted_meta_settings(runtime)
    with runtime.sessions() as session:
        conversation = session.scalars(select(ConversationModel)).one()
        conversation.extra_data = {}
        session.commit()
    client = FakeWhatsAppCloudApiClient()
    monkeypatch.setattr(
        "app.operations.ai_consumer.get_whatsapp_cloud_api_client", lambda _: client
    )
    assert await dispatch_one(runtime.service)
    assert not client.calls
