from collections.abc import Generator
from typing import Any
from uuid import uuid4

import pytest
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.generative_ai.policy import config_hash, conversation_allowed
from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
from app.channels.whatsapp.live_mapper import (
    WhatsAppInboundMessageMapper,
    WhatsAppWebhookParser,
)
from app.domain.generative_ai.contracts import AIConfig
from app.domain.whatsapp_live.contracts import WhatsAppBusinessAppEcho
from app.infrastructure.database import Base
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations.ai_consumer import dispatch_one
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from tests.test_generative_ai import Runtime
from tests.test_whatsapp_live_contracts_mapper import context, payload, text_message
from tests.test_whatsapp_live_processor_repository import cipher, parsed


@pytest.fixture
def runtime(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Generator[Runtime]:
    engine = create_engine(f"sqlite:///{tmp_path / 'ads.db'}")
    Base.metadata.create_all(engine)
    yield Runtime(sessionmaker(bind=engine, autoflush=False), monkeypatch)
    engine.dispose()


@pytest.mark.parametrize(
    ("referral", "expected"),
    [
        ({"source_type": "ad", "source_id": "12345"}, "12345"),
        ({"source_type": "post", "source_id": "12345"}, None),
        ({"source_type": "ad"}, None),
        ({"source_type": "ad", "source_id": "x"}, None),
        ({"source_type": "ad", "source_id": "1" * 65}, None),
        ({"source_type": "ad", "source_id": 12345}, None),
        ({"source_type": "ad", "source_id": "١٢٣"}, None),
        ("ad", None),
        (None, None),
    ],
)
def test_only_valid_structured_ad_referral_is_retained(
    referral: object, expected: str | None
) -> None:
    raw = text_message()
    raw.update(text={"body": "Vengo del anuncio source_type=ad"}, referral=referral)
    candidate = WhatsAppWebhookParser().parse(payload(raw), max_events=1).messages[0]
    inbound = WhatsAppInboundMessageMapper().map(candidate, context())
    assert inbound is not None
    assert candidate.ad_source_id == expected
    assert inbound.metadata.get("whatsapp_ad_source_id") == expected
    assert set(inbound.metadata) <= {"message_type", "whatsapp_ad_source_id"}


def configure(runtime: Runtime, **changes: Any) -> None:
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        existing = AIConfig.model_validate(bot.settings["generative_ai"]).model_dump()
        bot.settings = {
            **bot.settings,
            "generative_ai": {**existing, **changes},
        }
        session.commit()


async def inbound(
    runtime: Runtime,
    message_id: str,
    source_id: str | None = None,
    sender: str = "51999999999",
) -> None:
    event = parsed(runtime.channel.phone_number_id, message_id)
    event = event.model_copy(
        update={
            "messages": (
                event.messages[0].model_copy(
                    update={
                        "ad_source_id": source_id,
                        "external_sender_id": sender,
                        "text": "Mi sobrino tiene 5 años y quiere un dinosaurio",
                    }
                ),
            )
        }
    )
    with runtime.sessions() as session:
        await get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        ).process(
            event,
            public_webhook_id=runtime.channel.public_webhook_id,
            correlation_id=uuid4(),
        )


async def test_organic_keeps_history_without_ai_or_legacy_reply(
    runtime: Runtime,
) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "organic")
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        assert len(session.scalars(select(MessageModel)).all()) == 1
        assert not session.scalars(select(AIJobModel)).all()
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()
    assert not runtime.provider.calls


async def test_ad_origin_survives_duplicate_and_followup_without_referral(
    runtime: Runtime,
) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "ad-1", "12345")
    await inbound(runtime, "ad-1", "99999")
    await inbound(runtime, "followup")
    assert await runtime.service.run_once()
    with runtime.sessions() as session:
        conversation = session.scalars(select(ConversationModel)).one()
        origin = (conversation.extra_data or {}).get("whatsapp_ad_origin")
        assert isinstance(origin, dict) and origin["source_id"] == "12345"
        assert len(session.scalars(select(MessageModel)).all()) == 2
        assert len(session.scalars(select(AIJobModel)).all()) == 2
    assert runtime.provider.calls
    assert all("whatsapp_ads_only" not in c["config"] for c in runtime.provider.calls)


async def test_ads_never_bypass_pilot_recipient_restriction(runtime: Runtime) -> None:
    configure(runtime, whatsapp_ads_only=True, pilot_recipients=[])
    await inbound(runtime, "blocked-ad", "12345")
    with runtime.sessions() as session:
        assert not session.scalars(select(AIJobModel)).all()
    assert not runtime.provider.calls


async def test_ad_origin_does_not_qualify_another_customer(runtime: Runtime) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "first-ad", "12345")
    await inbound(runtime, "second-organic", sender="51988888888")
    with runtime.sessions() as session:
        assert len(session.scalars(select(ConversationModel)).all()) == 2
        assert len(session.scalars(select(AIJobModel)).all()) == 1


async def test_enabling_ads_filter_cancels_existing_organic_job(
    runtime: Runtime,
) -> None:
    await inbound(runtime, "before-ads-only")
    configure(runtime, whatsapp_ads_only=True)
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
    assert not runtime.provider.calls


async def test_human_phone_reply_still_blocks_ad_followup(runtime: Runtime) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "ad-before-human", "12345")
    event = parsed(runtime.channel.phone_number_id)
    echo = WhatsAppBusinessAppEcho(
        external_message_id="human-echo",
        external_recipient_id="51999999999",
        phone_number_id=runtime.channel.phone_number_id,
        timestamp=event.messages[0].timestamp,
        message_type="text",
        text="Un asesor atiende esta consulta.",
    )
    with runtime.sessions() as session:
        await get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        ).process(
            event.model_copy(update={"messages": (), "echoes": (echo,)}),
            public_webhook_id=runtime.channel.public_webhook_id,
            correlation_id=uuid4(),
        )
    await inbound(runtime, "ad-after-human", "12345")
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        jobs = session.scalars(select(AIJobModel)).all()
        assert len(jobs) == 1 and jobs[0].status == "cancelled"
    assert not runtime.provider.calls


@pytest.mark.parametrize("ready", [False, True])
async def test_removing_origin_blocks_queued_or_ready_work(
    runtime: Runtime, ready: bool
) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "ad-work", "12345")
    if ready:
        assert await runtime.service.run_once()
    with runtime.sessions() as session:
        conversation = session.scalars(select(ConversationModel)).one()
        conversation.extra_data = {}
        session.commit()
    if ready:
        await dispatch_one(runtime.service)
    else:
        assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_retry_revalidates_ad_origin(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(runtime, whatsapp_ads_only=True)
    await inbound(runtime, "retry-ad", "12345")
    assert await runtime.service.run_once()

    async def defer(*args: Any, **kwargs: Any) -> bool:
        return False

    with monkeypatch.context() as patch:
        patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", defer)
        await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        conversation = session.scalars(select(ConversationModel)).one()
        conversation.extra_data = {}
        session.commit()
    with runtime.sessions() as session:
        attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert not await get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        ).retry_attempt(attempt.id)
        assert attempt.last_error_code == "AI_POLICY_CHANGED"


def test_origin_is_line_scoped_and_default_hash_compatible() -> None:
    import hashlib

    config = AIConfig()
    old_json = config.model_dump_json(
        exclude={
            "conversational_response",
            "pilot_recipients",
            "whatsapp_ads_only",
            "handoff_adviser_name",
        }
    )
    assert config_hash(config) == hashlib.sha256(old_json.encode()).hexdigest()
    assert config_hash(config) != config_hash(AIConfig(whatsapp_ads_only=True))
    line = uuid4()
    conversation = ConversationModel(
        channel="whatsapp",
        channel_configuration_id=line,
        extra_data={
            "whatsapp_ad_origin": {"source_id": "12345", "configuration_id": str(line)}
        },
    )
    assert conversation_allowed(AIConfig(whatsapp_ads_only=True), conversation, line)
    assert not conversation_allowed(
        AIConfig(whatsapp_ads_only=True), conversation, uuid4()
    )
