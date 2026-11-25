import hashlib
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.generative_ai.policy import (
    job_route_matches,
    pending_handoff_notice,
)
from app.domain.whatsapp_live.contracts import (
    AdviserAlertConfig,
    WhatsAppTemplateMessage,
)
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.security.secret_cipher import SecretCipher, SecretCipherError

ALERT_PREFIX = "adviser-alert:"
_PHONE = re.compile(r"[1-9][0-9]{7,14}")
_USERNAME = re.compile(r"[a-zA-Z0-9_.]{1,64}")
_LINK = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_SENSITIVE = re.compile(
    r"\b(?:contraseñas?|passwords?|tokens?|otp|cvv|pin|c[oó]digo de verificaci[oó]n|"
    r"c[oó]digo de seguridad|tarjeta de (?:cr[eé]dito|d[eé]bito))\b",
    re.IGNORECASE,
)
_DIGITS = re.compile(r"(?<!\w)\d(?:[ .-]?\d){5,}(?!\w)")


def configuration_digest(config: AdviserAlertConfig) -> str:
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()


def enqueue_adviser_alert(
    session: Session,
    cipher: SecretCipher,
    job: AIJobModel,
    handoff_id: UUID,
    version: int,
    config: AdviserAlertConfig,
) -> None:
    key = f"{ALERT_PREFIX}{handoff_id}:{version}"
    existing = session.scalar(
        select(OutboundMessageAttemptModel.id).where(
            OutboundMessageAttemptModel.organization_id == job.organization_id,
            OutboundMessageAttemptModel.idempotency_key == key,
        )
    )
    if existing is not None:
        return
    now = datetime.now(UTC)
    session.add(
        OutboundMessageAttemptModel(
            idempotency_key=key,
            inbound_receipt_id=job.receipt_id,
            notification=True,
            organization_id=job.organization_id,
            bot_id=job.bot_id,
            channel_configuration_id=job.configuration_id,
            external_recipient_hash=hashlib.sha256(
                config.recipient.encode()
            ).hexdigest(),
            external_recipient_ciphertext=cipher.encrypt(config.recipient),
            message_ciphertext=cipher.encrypt(configuration_digest(config)),
            status="pending",
            attempt_count=0,
            created_at=now,
            updated_at=now,
        )
    )


def build_adviser_template(
    session: Session,
    cipher: SecretCipher,
    attempt: OutboundMessageAttemptModel,
    config: AdviserAlertConfig,
) -> WhatsAppTemplateMessage | None:
    if not attempt.notification or attempt.reply_to_external_message_id is not None:
        return None
    job = session.scalar(
        select(AIJobModel).where(
            AIJobModel.receipt_id == attempt.inbound_receipt_id,
            AIJobModel.organization_id == attempt.organization_id,
            AIJobModel.bot_id == attempt.bot_id,
            AIJobModel.configuration_id == attempt.channel_configuration_id,
        )
    )
    if job is None:
        return None
    conversation = session.get(ConversationModel, job.conversation_id)
    suffix = (attempt.idempotency_key or "").removeprefix(ALERT_PREFIX)
    # Hold the same handoff lock as customer notices while reading the snapshot.
    if (
        conversation is None
        or conversation.management_status in {"closed", "archived"}
        or not job_route_matches(session, job, conversation)
        or not pending_handoff_notice(session, job, f"ai:{job.id}:handoff:{suffix}")
    ):
        return None
    messages = list(
        session.scalars(
            select(MessageModel)
            .where(
                MessageModel.organization_id == job.organization_id,
                MessageModel.bot_id == job.bot_id,
                MessageModel.conversation_id == conversation.id,
                MessageModel.channel_type == "whatsapp",
                MessageModel.direction == "inbound",
                MessageModel.text_ciphertext.is_not(None),
            )
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(3)
        )
    )
    usable = [
        message
        for message in messages
        if not (message.metadata_data or {}).get("business_app_content_invalidated")
    ]
    contact = _contact_label(session, cipher, conversation, usable)
    excerpts = []
    for message in reversed(usable):
        content = _decrypt(cipher, message.text_ciphertext)
        if content and not _SENSITIVE.search(content):
            clean = _DIGITS.sub(
                "[dato omitido]", _LINK.sub("[enlace omitido]", content)
            )
            if excerpt := _preview(clean, 125):
                excerpts.append(excerpt)
    context = " / ".join(excerpts) or "Consulta el historial en Luri."
    link = (
        f"{config.portal_origin}/portal?org={job.organization_id}"
        f"&conversation={conversation.id}"
    )
    return WhatsAppTemplateMessage(
        name=config.template_name,
        language=config.language,
        parameters=(contact, context, link),
    )


def _contact_label(
    session: Session,
    cipher: SecretCipher,
    conversation: ConversationModel,
    messages: list[MessageModel],
) -> str:
    customer_id = conversation.external_customer_id or ""
    if _PHONE.fullmatch(customer_id):
        return f"+{customer_id}"
    for message in messages:
        encrypted = (message.extra_data or {}).get("whatsapp_username_ciphertext")
        username = _decrypt(cipher, encrypted if isinstance(encrypted, str) else None)
        if username and _USERNAME.fullmatch(username):
            return f"@{username}"
    if conversation.contact_id is not None:
        record = session.get(ContactModel, conversation.contact_id)
        if (
            record is not None
            and record.organization_id == conversation.organization_id
            and record.channel_type == "whatsapp"
            and record.status == "active"
        ):
            name = _decrypt(cipher, record.display_name_ciphertext)
            if name and (label := _preview(name, 64)):
                return label
    return "Consulta el contacto en Luri."


def _decrypt(cipher: SecretCipher, ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    try:
        return cipher.decrypt(ciphertext)
    except SecretCipherError:
        return None


def _preview(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
