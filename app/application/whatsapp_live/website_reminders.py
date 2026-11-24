"""Schedule fixed WhatsApp follow-ups for a new, unanswered Ads lead."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.generative_ai.policy import (
    configuration,
    conversation_allowed,
    job_policy_hash,
    job_route_matches,
    recipient_allowed,
)
from app.application.generative_ai.service import utc
from app.domain.generative_ai.contracts import ProviderError
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)
from app.infrastructure.settings import Settings

ReminderStep = Literal[1, 2]
# Older workers reject orphan ai: attempts instead of delivering these as
# ordinary replies if this feature is rolled back while reminders are pending.
REMINDER_PREFIX = "ai:website-reminder:"
REMINDER_TERMINAL_SENT = ("sent", "delivered", "read")
DELIVERY_LEASE = timedelta(seconds=120)
FIRST_DELAY = timedelta(hours=4)
LAST_DELAY = timedelta(hours=12)
REMINDER_STEPS: tuple[ReminderStep, ...] = (1, 2)
REMINDER_TEXT = {
    1: (
        "Si quieres avanzar con tu web, cuéntame a qué se dedica tu negocio. "
        "Con ese dato puedo orientarte sobre qué tipo de página te conviene."
    ),
    2: (
        "Dejo tu consulta abierta por aquí. Si quieres retomarla, dime qué "
        "necesitas que haga tu web y te ayudo a elegir por dónde empezar."
    ),
}


def reminder_key(job_id: UUID, step: ReminderStep) -> str:
    return f"{REMINDER_PREFIX}{job_id}:{step}"


def next_sending_time(instant: datetime, zone: ZoneInfo) -> datetime:
    local = utc(instant).astimezone(zone)
    if time(8) <= local.time() <= time(21):
        return local.astimezone(UTC)
    day = local.date() + timedelta(days=local.time() > time(21))
    return datetime.combine(day, time(8), tzinfo=zone).astimezone(UTC)


def reminder_due_at(
    greeting_sent: datetime,
    zone: ZoneInfo,
    *,
    previous_sent: datetime | None = None,
) -> datetime:
    greeting = utc(greeting_sent)
    due = greeting + FIRST_DELAY
    if previous_sent is not None:
        due = max(greeting + LAST_DELAY, utc(previous_sent) + FIRST_DELAY)
    return next_sending_time(due, zone)


@dataclass(frozen=True)
class ReminderDelivery:
    conversation_id: UUID
    recipient: str
    text: str


def prepare_reminder(
    session: Session,
    settings: Settings,
    attempt: OutboundMessageAttemptModel,
    now: datetime,
) -> ReminderDelivery | None:
    """Validate and lock before delivery. Return None when rescheduling."""
    key = attempt.idempotency_key or ""
    parts = key.removeprefix(REMINDER_PREFIX).split(":")
    try:
        job_id = UUID(parts[0])
    except ValueError as exc:
        raise ProviderError("REMINDER_ROUTE_CHANGED") from exc
    if len(parts) != 2 or parts[1] not in ("1", "2"):
        raise ProviderError("REMINDER_ROUTE_CHANGED")
    step: ReminderStep = 1 if parts[1] == "1" else 2
    job = session.get(AIJobModel, job_id)
    if (
        job is None
        or job.sequence != 1
        or attempt.notification
        or attempt.organization_id != job.organization_id
        or attempt.bot_id != job.bot_id
        or attempt.inbound_receipt_id != job.receipt_id
        or attempt.channel_configuration_id != job.configuration_id
        or key != reminder_key(job_id, step)
    ):
        raise ProviderError("REMINDER_ROUTE_CHANGED")
    bot = session.get(BotModel, job.bot_id)
    channel = session.get(WhatsAppChannelConfigurationModel, job.configuration_id)
    receipt = session.get(InboundMessageReceiptModel, job.receipt_id)
    conversation = session.get(
        ConversationModel, job.conversation_id, with_for_update=True
    )
    config = configuration(session, settings, job.organization_id, job.bot_id)
    if (
        config is None
        or not config.website_sales_follow_up
        or bot is None
        or channel is None
        or channel.status != "active"
        or not channel.webhook_enabled
        or channel.organization_id != job.organization_id
        or channel.bot_id != job.bot_id
        or receipt is None
        or conversation is None
        or conversation.management_status != "open"
        or conversation.inbound_message_count != job.sequence
        or conversation.last_inbound_at is None
        or not conversation.external_customer_id
        or not job_route_matches(session, job, conversation)
        or not conversation_allowed(config, conversation, job.configuration_id)
        or not recipient_allowed(config, conversation.external_customer_id)
        or job_policy_hash(
            config,
            conversation,
            channel.id,
            job.receipt_id,
            job.sequence,
            channel.phone_number_id,
        )
        != job.config_hash
    ):
        raise ProviderError("REMINDER_NO_LONGER_ELIGIBLE")
    handoff = session.scalar(
        select(HandoffSessionModel).where(
            HandoffSessionModel.conversation_id == conversation.id,
            HandoffSessionModel.organization_id == job.organization_id,
            HandoffSessionModel.bot_id == job.bot_id,
        )
    )
    if handoff and (handoff.status != "bot_active" or handoff.requested_at is not None):
        raise ProviderError("REMINDER_HUMAN_INTERVENED")

    expires = min(utc(receipt.received_at), utc(conversation.last_inbound_at))
    expires += timedelta(hours=24)
    try:
        zone = ZoneInfo(bot.timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ProviderError("REMINDER_INVALID_TIMEZONE") from exc
    due = next_sending_time(now, zone)
    if due >= expires:
        raise ProviderError("REMINDER_WINDOW_CLOSED")
    greeting = (
        session.get(OutboundMessageAttemptModel, job.outbound_id)
        if job.outbound_id
        else None
    )
    if (
        greeting is None
        or greeting.idempotency_key != f"ai:{job.id}"
        or greeting.organization_id != job.organization_id
        or greeting.bot_id != job.bot_id
        or greeting.channel_configuration_id != job.configuration_id
        or greeting.inbound_receipt_id != job.receipt_id
        or greeting.status not in REMINDER_TERMINAL_SENT
        or greeting.sent_at is None
    ):
        raise ProviderError("REMINDER_GREETING_NOT_SENT")

    if step == 1:
        due = max(due, reminder_due_at(greeting.sent_at, zone))
    else:
        first = session.scalar(
            select(OutboundMessageAttemptModel).where(
                OutboundMessageAttemptModel.organization_id == job.organization_id,
                OutboundMessageAttemptModel.idempotency_key == reminder_key(job.id, 1),
            )
        )
        if (
            first is None
            or first.status == "failed"
            or first.bot_id != job.bot_id
            or first.channel_configuration_id != job.configuration_id
            or first.inbound_receipt_id != job.receipt_id
        ):
            raise ProviderError("REMINDER_FIRST_NOT_SENT")
        if first.status not in REMINDER_TERMINAL_SENT or first.sent_at is None:
            # A delayed or retried first send must have a known send timestamp.
            due = next_sending_time(max(due, utc(now) + timedelta(minutes=5)), zone)
        else:
            due = max(
                due,
                reminder_due_at(greeting.sent_at, zone, previous_sent=first.sent_at),
            )
    if due >= expires:
        raise ProviderError("REMINDER_WINDOW_CLOSED")
    if due > utc(now):
        attempt.next_attempt_at = due
        return None
    return ReminderDelivery(
        conversation.id, conversation.external_customer_id, REMINDER_TEXT[step]
    )
