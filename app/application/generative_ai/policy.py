import hashlib
import json
import re
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.generative_ai.contracts import AIConfig
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
)
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
    # Preserve the legacy configuration digest; new jobs add a routing snapshot.
    excluded = {"conversational_response"}
    if config.pilot_recipients is None:
        excluded.add("pilot_recipients")
    if not config.whatsapp_ads_only:
        excluded.add("whatsapp_ads_only")
    if config.handoff_adviser_name is None:
        excluded.add("handoff_adviser_name")
    if not config.website_sales_intake:
        excluded.add("website_sales_intake")
    if not config.website_sales_follow_up:
        excluded.add("website_sales_follow_up")
    return hashlib.sha256(config.model_dump_json(exclude=excluded).encode()).hexdigest()


def recipient_allowed(config: AIConfig, recipient: str) -> bool:
    """None preserves existing bots; an explicit empty pilot list denies all."""
    return config.pilot_recipients is None or recipient in config.pilot_recipients


def handoff_notice_key(job: AIJobModel, handoff_id: UUID, version: int) -> str:
    return f"ai:{job.id}:handoff:{handoff_id}:{version}"


def pending_handoff_notice(session: Session, job: AIJobModel, key: str) -> bool:
    handoff = session.scalar(
        select(HandoffSessionModel)
        .where(
            HandoffSessionModel.conversation_id == job.conversation_id,
            HandoffSessionModel.organization_id == job.organization_id,
            HandoffSessionModel.bot_id == job.bot_id,
            HandoffSessionModel.status == "waiting_human",
            HandoffSessionModel.reason_code == "assistant_requested",
        )
        .with_for_update()
    )
    return handoff is not None and key == handoff_notice_key(
        job, handoff.id, handoff.version
    )


def job_route_matches(
    session: Session, job: AIJobModel, conversation: ConversationModel
) -> bool:
    receipt = session.get(InboundMessageReceiptModel, job.receipt_id)
    return (
        conversation.organization_id == job.organization_id
        and conversation.bot_id == job.bot_id
        and conversation.channel == "whatsapp"
        and conversation.channel_configuration_id == job.configuration_id
        and bool(conversation.external_customer_id)
        and receipt is not None
        and receipt.organization_id == job.organization_id
        and receipt.bot_id == job.bot_id
        and receipt.channel_type == "whatsapp"
        and receipt.channel_configuration_id == job.configuration_id
    )


def job_policy_hash(
    config: AIConfig,
    conversation: ConversationModel,
    configuration_id: UUID,
    receipt_id: UUID,
    sequence: int,
    external_channel_id: str,
) -> str:
    """Bind new jobs to their immutable routing snapshot as well as config."""
    data = {
        "version": "routing-v1",
        "config_hash": config_hash(config),
        "organization_id": str(conversation.organization_id),
        "bot_id": str(conversation.bot_id),
        "conversation_id": str(conversation.id),
        "configuration_id": str(configuration_id),
        "external_channel_id": external_channel_id,
        "receipt_id": str(receipt_id),
        "recipient": conversation.external_customer_id,
        "sequence": sequence,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


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
