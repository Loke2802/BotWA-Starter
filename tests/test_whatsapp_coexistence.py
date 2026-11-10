import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.channels.whatsapp.live_mapper import (
    WhatsAppWebhookParser,
    WhatsAppWebhookPayloadError,
)
from app.domain.whatsapp_live.contracts import (
    WhatsAppBusinessAppEcho,
    WhatsAppParsedWebhook,
)
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations.ai_consumer import dispatch_one
from sqlalchemy import select

from tests.test_generative_ai import Runtime
from tests.test_generative_ai import runtime as runtime
from tests.test_whatsapp_live_processor_repository import cipher, parsed


def candidate(runtime: Runtime, **updates: object) -> WhatsAppBusinessAppEcho:
    return WhatsAppBusinessAppEcho.model_validate(
        {
            "external_message_id": "wamid.business-app-1",
            "external_recipient_id": "51999999999",
            "phone_number_id": runtime.channel.phone_number_id,
            "timestamp": datetime.now(UTC),
            "message_type": "text",
            "text": "Un asesor ya está atendiendo tu consulta.",
            **updates,
        }
    )


async def receive(runtime: Runtime, echo: WhatsAppBusinessAppEcho) -> None:
    with runtime.sessions() as session:
        processor = get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        )
        await processor.process(
            WhatsAppParsedWebhook(echoes=(echo,)),
            public_webhook_id=runtime.channel.public_webhook_id,
            correlation_id=uuid4(),
        )


def raw_echo(*, field: str = "smb_message_echoes", count: int = 1) -> bytes:
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": field,
                            "value": {
                                "metadata": {"phone_number_id": "test-phone"},
                                "message_echoes": [
                                    {
                                        "from": "15550000001",
                                        "to": "15550000002",
                                        "id": "wamid.echo",
                                        "type": "text",
                                        "timestamp": "1794230000",
                                        "text": {"body": "Atención humana"},
                                    }
                                ]
                                * count,
                            },
                        }
                    ]
                }
            ],
        }
    ).encode()


def test_parser_keeps_echoes_separate_and_ignores_history() -> None:
    parser = WhatsAppWebhookParser()
    payload = parser.parse(raw_echo(), max_events=5)
    assert not payload.messages and not payload.statuses
    assert len(payload.echoes) == 1
    assert payload.echoes[0].external_recipient_id == "15550000002"
    assert not parser.parse(raw_echo(field="history"), max_events=5).echoes
    assert not parser.parse(raw_echo(field="messages"), max_events=5).echoes
    with pytest.raises(WhatsAppWebhookPayloadError, match="limit"):
        parser.parse(raw_echo(count=2), max_events=1)


async def test_echo_is_encrypted_durable_and_never_sent(runtime: Runtime) -> None:
    echo = candidate(runtime)
    await receive(runtime, echo)
    # Another session simulates webhook retry after a process restart.
    await receive(runtime, echo)
    with runtime.sessions() as session:
        message = session.scalars(select(MessageModel)).one()
        conversation = session.scalars(select(ConversationModel)).one()
        handoff = session.scalars(select(HandoffSessionModel)).one()
        assert message.role == "human" and message.direction == "outbound"
        assert message.content == "" and message.author_user_id is None
        assert echo.text is not None
        assert message.text_ciphertext and echo.text not in message.text_ciphertext
        assert cipher().decrypt(message.text_ciphertext) == echo.text
        assert conversation.message_count == conversation.outbound_message_count == 1
        assert conversation.inbound_message_count == 0
        assert handoff.status == "waiting_human"
        assert handoff.assigned_user_id is None
        assert handoff.reason_code == "business_app_reply"
        assert not session.scalars(select(AIJobModel)).all()
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()
    assert not runtime.provider.calls


async def test_echo_blocks_new_input_and_pending_generation(runtime: Runtime) -> None:
    await runtime.inbound()
    await receive(runtime, candidate(runtime))
    await runtime.inbound("after-human")
    assert not await runtime.service.run_once()
    assert not await dispatch_one(runtime.service)
    assert not runtime.provider.calls
    with runtime.sessions() as session:
        jobs = session.scalars(select(AIJobModel)).all()
        assert len(jobs) == 1 and jobs[0].status == "cancelled"
        assert jobs[0].error_code == "BUSINESS_APP_REPLY"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_echo_cancels_ready_response(runtime: Runtime) -> None:
    await runtime.inbound()
    assert await runtime.service.run_once()
    await receive(runtime, candidate(runtime))
    assert not await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_echo_during_generation_fences_stale_owner(runtime: Runtime) -> None:
    await runtime.inbound()

    def interrupt() -> None:
        # Provider's callback runs after the generation DB transaction is closed.
        from app.application.whatsapp_live.coexistence import BusinessAppEchoService
        from app.domain.channel.contracts import ResolvedChannelContext
        from app.infrastructure.unit_of_work import atomic_transport

        with runtime.sessions() as session, atomic_transport(session):
            BusinessAppEchoService(session, cipher()).record(
                candidate(runtime),
                ResolvedChannelContext(
                    channel_type="whatsapp",
                    organization_id=runtime.channel.organization_id,
                    bot_id=runtime.channel.bot_id,
                    channel_configuration_id=runtime.channel.id,
                    external_channel_id=runtime.channel.phone_number_id,
                ),
            )
            session.commit()

    runtime.provider.on_call = interrupt
    assert await runtime.service.run_once()
    assert len(runtime.provider.calls) == 1
    assert not await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "cancelled" and job.token is None


async def test_duplicate_does_not_reopen_returned_handoff(runtime: Runtime) -> None:
    echo = candidate(runtime)
    await receive(runtime, echo)
    with runtime.sessions() as session:
        handoff = session.scalars(select(HandoffSessionModel)).one()
        handoff.status = "bot_active"
        session.commit()
    await receive(runtime, echo)
    with runtime.sessions() as session:
        assert session.scalars(select(HandoffSessionModel)).one().status == "bot_active"


async def test_wrong_phone_cannot_persist_or_block(runtime: Runtime) -> None:
    from app.application.whatsapp_live.processor import WhatsAppRuntimeRoutingError

    await runtime.inbound()
    with pytest.raises(WhatsAppRuntimeRoutingError):
        await receive(runtime, candidate(runtime, phone_number_id="other-phone"))
    with runtime.sessions() as session:
        assert not session.scalars(select(HandoffSessionModel)).all()
        assert session.scalars(select(AIJobModel)).one().status == "pending"
        assert not session.scalars(
            select(MessageModel).where(MessageModel.direction == "outbound")
        ).all()


async def test_same_envelope_echo_precedes_inbound(runtime: Runtime) -> None:
    with runtime.sessions() as session:
        processor = get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        )
        payload = parsed(runtime.channel.phone_number_id).model_copy(
            update={"echoes": (candidate(runtime),)}
        )
        await processor.process(
            payload,
            public_webhook_id=runtime.channel.public_webhook_id,
            correlation_id=uuid4(),
        )
    with runtime.sessions() as session:
        assert not session.scalars(select(AIJobModel)).all()
        assert session.scalars(select(ConversationModel)).one().message_count == 2


async def test_nontext_intervention_still_blocks(runtime: Runtime) -> None:
    await receive(runtime, candidate(runtime, message_type="image", text=None))
    await runtime.inbound()
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        assert (
            session.scalars(select(HandoffSessionModel)).one().status == "waiting_human"
        )


async def test_edit_keeps_original_encrypted_history(runtime: Runtime) -> None:
    echo = candidate(runtime)
    await receive(runtime, echo)
    await receive(
        runtime, echo.model_copy(update={"message_type": "edit", "text": None})
    )
    with runtime.sessions() as session:
        original = session.scalars(
            select(MessageModel).where(MessageModel.message_type == "text")
        ).one()
        assert original.text_ciphertext
        assert cipher().decrypt(original.text_ciphertext) == echo.text
        assert (original.metadata_data or {}).get("business_app_content_invalidated")


async def test_echo_cancels_enqueued_delivery(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor

    await runtime.inbound()
    await runtime.service.run_once()

    async def defer(*args: object, **kwargs: object) -> bool:
        return False

    with monkeypatch.context() as patch:
        patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", defer)
        await dispatch_one(runtime.service)
    await receive(runtime, candidate(runtime))
    with runtime.sessions() as session:
        attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert attempt.status == "failed"
        assert attempt.last_error_code == "BUSINESS_APP_REPLY"
        message = session.scalars(
            select(MessageModel).where(MessageModel.outbound_attempt_id == attempt.id)
        ).one()
        assert message.delivery_status == "failed"
        processor = get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        )
        assert not await processor.retry_attempt(attempt.id)


async def test_echo_transaction_rolls_back_and_can_retry(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.application.human_handoff.service import HumanHandoffService

    original = HumanHandoffService.observe_business_app_reply

    def fail(*args: object, **kwargs: object) -> None:
        raise ValueError("controlled failure")

    with monkeypatch.context() as patch:
        patch.setattr(HumanHandoffService, "observe_business_app_reply", fail)
        with pytest.raises(ValueError, match="controlled failure"):
            await receive(runtime, candidate(runtime))
    with runtime.sessions() as session:
        assert not session.scalars(select(MessageModel)).all()
        assert not session.scalars(select(HandoffSessionModel)).all()
    assert HumanHandoffService.observe_business_app_reply is original
    await receive(runtime, candidate(runtime))
    with runtime.sessions() as session:
        assert session.scalars(select(MessageModel)).one().direction == "outbound"


async def test_same_waba_other_line_does_not_block_first_line(runtime: Runtime) -> None:
    from app.application.whatsapp_live.processor import WhatsAppRuntimeRoutingError

    from tests.test_whatsapp_live_processor_repository import configuration

    await runtime.inbound()
    with runtime.sessions() as session:
        other = configuration(cipher(), phone_number_id="another-line")
        other.organization_id = runtime.channel.organization_id
        other.bot_id = runtime.channel.bot_id
        other.whatsapp_business_account_id = (
            runtime.channel.whatsapp_business_account_id
        )
        session.add(other)
        session.commit()
        webhook_id, phone = other.public_webhook_id, other.phone_number_id
    echo = candidate(runtime, phone_number_id=phone)
    with pytest.raises(WhatsAppRuntimeRoutingError):
        await receive(runtime, echo)
    with runtime.sessions() as session:
        processor = get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        )
        await processor.process(
            WhatsAppParsedWebhook(echoes=(echo,)),
            public_webhook_id=webhook_id,
            correlation_id=uuid4(),
        )
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "pending"
        handoff = session.scalars(select(HandoffSessionModel)).one()
        first = session.scalars(select(AIJobModel)).one()
        assert handoff.conversation_id != first.conversation_id
