"""Scoped permission for ad-origin replies; never grants global transport access."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.generative_ai.policy import (
    configuration,
    conversation_allowed,
    recipient_allowed,
)
from app.domain.channel.contracts import ResolvedChannelContext
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.settings import Settings


def ad_recipient_allowed(
    session: Session,
    settings: Settings,
    recipient: str,
    context: ResolvedChannelContext,
) -> bool:
    if (
        context.channel_type != "whatsapp"
        or settings.whatsapp_live_client_mode != "meta"
    ):
        return False
    channel = session.scalar(
        select(WhatsAppChannelConfigurationModel.id).where(
            WhatsAppChannelConfigurationModel.id == context.channel_configuration_id,
            WhatsAppChannelConfigurationModel.organization_id
            == context.organization_id,
            WhatsAppChannelConfigurationModel.bot_id == context.bot_id,
            WhatsAppChannelConfigurationModel.phone_number_id
            == context.external_channel_id,
            WhatsAppChannelConfigurationModel.status == "active",
            WhatsAppChannelConfigurationModel.webhook_enabled.is_(True),
        )
    )
    if channel is None:
        return False
    config = configuration(session, settings, context.organization_id, context.bot_id)
    if (
        config is None
        or not config.whatsapp_ads_only
        or not recipient_allowed(config, recipient)
    ):
        return False
    conversations = session.scalars(
        select(ConversationModel).where(
            ConversationModel.organization_id == context.organization_id,
            ConversationModel.bot_id == context.bot_id,
            ConversationModel.channel_configuration_id
            == context.channel_configuration_id,
            ConversationModel.channel == "whatsapp",
            ConversationModel.external_customer_id == recipient,
        )
    )
    return any(
        conversation_allowed(config, row, context.channel_configuration_id)
        for row in conversations
    )
