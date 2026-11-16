import hashlib
import re
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.generative_ai.contracts import AIConfig
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.settings import Settings


def configuration(
    session: Session, settings: Settings, organization_id: UUID, bot_id: UUID
) -> AIConfig | None:
    if not settings.ai_enabled or (
        f"{organization_id}:{bot_id}" not in settings.ai_pilot_scopes
    ):
        return None
    bot = session.get(BotModel, bot_id)
    org = session.get(OrganizationModel, organization_id)
    if (
        bot is None
        or org is None
        or bot.organization_id != organization_id
        or bot.status != "active"
        or org.status != "active"
    ):
        return None
    try:
        config = AIConfig.model_validate((bot.settings or {}).get("generative_ai", {}))
    except ValidationError:
        return None
    return config if config.enabled else None


def config_hash(config: AIConfig) -> str:
    # Preserve PR44 hashes for queued jobs and configuration without the new flag.
    excluded = {"conversational_response"}
    if config.pilot_recipients is None:
        excluded.add("pilot_recipients")
    if not config.whatsapp_ads_only:
        excluded.add("whatsapp_ads_only")
    return hashlib.sha256(config.model_dump_json(exclude=excluded).encode()).hexdigest()


def recipient_allowed(config: AIConfig, recipient: str) -> bool:
    """None preserves existing bots; an explicit empty pilot list denies all."""
    return config.pilot_recipients is None or recipient in config.pilot_recipients


def record_ad_origin(
    conversation: ConversationModel, source_id: object, configuration_id: UUID
) -> None:
    """Called only from authenticated WhatsApp ingress under the row lock."""
    if (
        conversation.channel != "whatsapp"
        or conversation.channel_configuration_id != configuration_id
        or not isinstance(source_id, str)
        or re.fullmatch(r"[0-9]{1,64}", source_id) is None
    ):
        return
    data = dict(conversation.extra_data or {})
    data["whatsapp_ad_origin"] = {
        "source_id": source_id,
        "configuration_id": str(configuration_id),
    }
    conversation.extra_data = data


def conversation_allowed(
    config: AIConfig, conversation: ConversationModel, configuration_id: UUID
) -> bool:
    if not config.whatsapp_ads_only:
        return True
    origin = (conversation.extra_data or {}).get("whatsapp_ad_origin")
    return (
        conversation.channel == "whatsapp"
        and conversation.channel_configuration_id == configuration_id
        and isinstance(origin, dict)
        and origin.get("configuration_id") == str(configuration_id)
        and isinstance(origin.get("source_id"), str)
        and re.fullmatch(r"[0-9]{1,64}", origin["source_id"]) is not None
    )
