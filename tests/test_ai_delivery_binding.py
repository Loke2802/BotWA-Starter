"""Synthetic routing regressions; fake provider/client, no real recipients."""

import hashlib
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations.ai_consumer import dispatch_one
from sqlalchemy import select

from tests.test_generative_ai import Runtime, runtime
from tests.test_whatsapp_live_processor_repository import cipher

__all__ = ["runtime"]


async def pending_attempt(runtime: Runtime, monkeypatch: pytest.MonkeyPatch) -> UUID:
    await runtime.inbound()
    assert await runtime.service.run_once()

    async def defer(*args: Any, **kwargs: Any) -> bool:
        return False

    with monkeypatch.context() as patch:
        patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", defer)
        await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        return session.scalars(select(OutboundMessageAttemptModel.id)).one()


def another_line(runtime: Runtime, session: Any) -> UUID:
    old = session.get(WhatsAppChannelConfigurationModel, runtime.channel.id)
    assert old is not None
    data = {c.key: getattr(old, c.key) for c in old.__table__.columns}
    data.update(id=uuid4(), phone_number_id="987654321", public_webhook_id=uuid4())
    row = WhatsAppChannelConfigurationModel(**data)
    session.add(row)
    session.flush()
    return row.id


@pytest.mark.parametrize(
    "mutation",
    [
        "recipient",
        "recipient_hash",
        "cipher_invalid",
        "line",
        "external_line",
        "webhook_off",
        "receipt",
        "idempotency",
        "idempotency_non_ai",
        "notification",
        "reply_context",
        "message_cipher",
    ],
)
async def test_ai_retry_never_uses_a_mismatched_delivery_target(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    attempt_id = await pending_attempt(runtime, monkeypatch)
    client = FakeWhatsAppCloudApiClient()
    with runtime.sessions() as session:
        attempt = session.get(OutboundMessageAttemptModel, attempt_id)
        assert attempt is not None
        if mutation == "recipient":
            attempt.external_recipient_ciphertext = cipher().encrypt("51977777777")
            attempt.external_recipient_hash = hashlib.sha256(b"51977777777").hexdigest()
        elif mutation == "recipient_hash":
            attempt.external_recipient_hash = "x" * 64
        elif mutation == "cipher_invalid":
            attempt.external_recipient_ciphertext = "invalid-ciphertext"
        elif mutation == "message_cipher":
            attempt.message_ciphertext = "invalid-ciphertext"
        elif mutation == "line":
            attempt.channel_configuration_id = another_line(runtime, session)
        elif mutation == "external_line":
            channel = session.get(WhatsAppChannelConfigurationModel, runtime.channel.id)
            assert channel is not None
            channel.phone_number_id = "987654321"
        elif mutation == "webhook_off":
            channel = session.get(WhatsAppChannelConfigurationModel, runtime.channel.id)
            assert channel is not None
            channel.webhook_enabled = False
        elif mutation == "idempotency":
            attempt.idempotency_key = "ai:another-job"
        elif mutation == "idempotency_non_ai":
            attempt.idempotency_key = "unrelated-key"
        elif mutation == "notification":
            attempt.notification = True
        elif mutation == "reply_context":
            attempt.reply_to_external_message_id = "wamid.unrelated"
        else:
            original = session.get(
                InboundMessageReceiptModel, attempt.inbound_receipt_id
            )
            assert original is not None
            data = {c.key: getattr(original, c.key) for c in original.__table__.columns}
            data.update(id=uuid4(), external_message_id="different-source-receipt")
            other = InboundMessageReceiptModel(**data)
            session.add(other)
            session.flush()
            attempt.inbound_receipt_id = other.id
        session.commit()
        delivered = await get_whatsapp_live_message_processor(
            session, cipher(), client, runtime.settings
        ).retry_attempt(attempt_id)
        assert not delivered
        assert not client.calls
        assert attempt.status == "failed"


async def test_queued_job_cannot_generate_for_another_line(runtime: Runtime) -> None:
    await runtime.inbound()
    with runtime.sessions() as session:
        conversation = session.scalars(select(ConversationModel)).one()
        conversation.channel_configuration_id = another_line(runtime, session)
        session.commit()
    assert not await runtime.service.run_once()
    assert not runtime.provider.calls


@pytest.mark.parametrize("ready", [False, True])
async def test_recipient_snapshot_change_cannot_redirect_a_job(
    runtime: Runtime, ready: bool
) -> None:
    await runtime.inbound()
    if ready:
        assert await runtime.service.run_once()
    with runtime.sessions() as session:
        conversation = session.scalars(select(ConversationModel)).one()
        conversation.external_customer_id = "51977777777"
        session.commit()
    if ready:
        await dispatch_one(runtime.service)
    else:
        assert not await runtime.service.run_once()
        assert not runtime.provider.calls
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_valid_reply_reaches_only_the_original_recipient_once(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt_id = await pending_attempt(runtime, monkeypatch)
    client = FakeWhatsAppCloudApiClient()
    with runtime.sessions() as session:
        processor = get_whatsapp_live_message_processor(
            session, cipher(), client, runtime.settings
        )
        assert await processor.retry_attempt(attempt_id)
        assert not await processor.retry_attempt(attempt_id)
        attempt = session.get(OutboundMessageAttemptModel, attempt_id)
        assert attempt and attempt.status == "sent"
    assert len(client.calls) == 1
    assert (
        client.calls[0]["recipient_hash"]
        == hashlib.sha256(b"51999999999").hexdigest()[:12]
    )
    assert (
        client.calls[0]["phone_number_hash"]
        == hashlib.sha256(runtime.channel.phone_number_id.encode()).hexdigest()[:12]
    )
