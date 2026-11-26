import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.generative_ai.service import AIService
from app.application.generative_ai.validation import (
    FALLBACK,
    apply_discovery,
    render,
    salvage,
)
from app.application.whatsapp_live.website_reminders import REMINDER_TEXT, reminder_key
from app.domain.bot.contracts import BotUpdate
from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    AIModel,
    Discovery,
    Generation,
    NeedDefinition,
    NeedPatch,
    ProviderError,
    ResponseConfig,
    Usage,
)
from app.domain.whatsapp_live.contracts import AdviserAlertConfig
from app.infrastructure.database import Base
from app.infrastructure.generative_ai.openai_provider import OpenAIProvider
from app.infrastructure.models.ai_generation import AIJobModel, AIMemoryModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)
from app.infrastructure.settings import Settings
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations import ai_consumer
from app.operations.ai_consumer import (
    dispatch_adviser_alert,
    dispatch_one,
    dispatch_website_reminder,
)
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tests.test_luri_stabilization import seed_channel, settings
from tests.test_whatsapp_live_processor_repository import cipher, parsed

CONFIG = AIConfig(
    enabled=True,
    needs=[
        NeedDefinition(
            key="age",
            question="¿Qué edad tiene?",
            kind="number",
            required=True,
            attribute="age",
            comparison="range",
        )
    ],
)


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error: ProviderError | None = None
        self.on_call: Any = None

    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        data = json.loads(context)
        self.calls.append(data)
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        response: BaseModel
        if stage == "discovery":
            message = next(
                m for m in reversed(data["history"]) if m["direction"] == "inbound"
            )
            response = Discovery(
                new_topic=False,
                needs=[
                    NeedPatch(
                        key="age",
                        value="5",
                        message_ref=message["ref"],
                        quote="tiene 5 años",
                    )
                ],
                search_terms=["dinosaurio"],
                handoff_requested=False,
            )
        else:
            ref = next(iter(data["sources"]), None)
            response = AdviserResult.model_validate(
                {
                    "tone": "options",
                    "question_key": None,
                    "handoff_requested": False,
                    "recommendations": (
                        [
                            {
                                "item_ref": ref,
                                "matches": [
                                    {"need_key": "age", "attribute_key": "age"}
                                ],
                            }
                        ]
                        if ref
                        else []
                    ),
                    "knowledge": [],
                }
            )
        return Generation(
            data=response.model_dump_json(),
            usage=Usage(input_tokens=50, output_tokens=20, model="gpt-6-luna"),
        )


class Runtime:
    def __init__(
        self, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.sessions = sessions
        self.provider = FakeProvider()
        with sessions() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                from tests.integration.test_transport_postgresql import seed

                self.channel = seed(session)
            else:
                self.channel = seed_channel(session, str(int(uuid4()) % 10**12))
            bot = session.get(BotModel, self.channel.bot_id)
            assert bot
            bot.settings = {"generative_ai": CONFIG.model_dump()}
            self.item_id = uuid4()
            session.add(
                KnowledgeEntryModel(
                    id=self.item_id,
                    organization_id=bot.organization_id,
                    bot_id=bot.id,
                    title="Dinosaurio",
                    content="Dinosaurio educativo",
                    status="published",
                    created_by_user_id=self.channel.created_by_user_id,
                    metadata_data={
                        "catalog_item": {
                            "name": "Dino",
                            "attributes": [
                                {
                                    "key": "age",
                                    "label": "Edad recomendada",
                                    "value": "4 a 7 años",
                                    "minimum": 4,
                                    "maximum": 7,
                                }
                            ],
                        }
                    },
                )
            )
            session.commit()
            session.refresh(self.channel)
            session.expunge(self.channel)
        self.settings = settings().model_copy(
            update={
                "ai_enabled": True,
                "ai_pilot_scopes": (
                    f"{self.channel.organization_id}:{self.channel.bot_id}",
                ),
            }
        )
        monkeypatch.setattr(
            "app.infrastructure.settings.get_settings", lambda: self.settings
        )
        self.service = AIService(sessions, self.settings, cipher(), self.provider)

    async def inbound(
        self,
        message_id: str = "test-ai-1",
        *,
        text: str = "Mi sobrino tiene 5 años y quiere un dinosaurio",
        ad_source_id: str | None = None,
    ) -> None:
        with self.sessions() as session:
            payload = parsed(self.channel.phone_number_id, message_id)
            payload = payload.model_copy(
                update={
                    "messages": (
                        payload.messages[0].model_copy(
                            update={"text": text, "ad_source_id": ad_source_id}
                        ),
                    )
                }
            )
            processor = get_whatsapp_live_message_processor(
                session, cipher(), FakeWhatsAppCloudApiClient(), self.settings
            )
            await processor.process(
                payload,
                public_webhook_id=self.channel.public_webhook_id,
                correlation_id=uuid4(),
            )


@pytest.fixture
def runtime(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Generator[Runtime]:
    engine = create_engine(f"sqlite:///{tmp_path / 'ai.db'}")
    Base.metadata.create_all(engine)
    yield Runtime(sessionmaker(bind=engine, autoflush=False), monkeypatch)
    engine.dispose()


@pytest.mark.parametrize(
    ("customer_id", "username", "expected_contact", "change_recipient", "outcome"),
    [
        ("15550100100", "demo_phone", "+15550100100", False, "sent"),
        ("PE.AbCd123", "demo_lead", "@demo_lead", False, "sent"),
        ("PE.AbCd123", None, "Consulta el contacto en Luri.", False, "sent"),
        ("15550100100", None, "", True, "failed"),
        ("15550100100", None, "+15550100100", False, "failed"),
        ("15550100100", None, "+15550100100", False, "unknown"),
    ],
)
async def test_private_whatsapp_adviser_alert(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    customer_id: str,
    username: str | None,
    expected_contact: str,
    change_recipient: bool,
    outcome: str,
) -> None:
    from app.application.human_handoff.service import (
        HandoffForbiddenError,
        HumanHandoffService,
    )
    from app.channels.whatsapp.live_mapper import WhatsAppWebhookParser
    from app.domain.user.contracts import User
    from app.infrastructure.models.business_configuration import (
        BusinessConfigurationModel,
    )
    from app.infrastructure.models.human_handoff import HandoffSessionModel
    from app.infrastructure.models.message import MessageModel
    from app.infrastructure.repositories.audit_repository import (
        SqlAlchemyAuditRepository,
    )
    from app.infrastructure.repositories.human_handoff_repository import (
        HumanHandoffRepository,
    )
    from app.infrastructure.whatsapp.meta_client import MetaWhatsAppCloudApiClient

    from tests.plan_support import allow_all_plan_enforcement

    monkeypatch.setattr(
        "app.operations.ai_consumer.PlanEnforcementService",
        lambda repository: allow_all_plan_enforcement(),
    )
    channel = runtime.channel
    scope = f"{channel.organization_id}:{channel.bot_id}:{channel.id}"
    alert_config = AdviserAlertConfig(
        recipient="15550100101",
        template_name="aviso_derivacion",
        language="es",
        portal_origin="https://luri.example.test",
    )
    runtime.settings.handoff_alert_scopes = {scope: alert_config}
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        bot.settings = {
            "generative_ai": CONFIG.model_copy(
                update={"handoff_adviser_name": "Alex", "whatsapp_ads_only": True}
            ).model_dump()
        }
        session.add(
            BusinessConfigurationModel(
                bot_id=bot.id,
                business_name="Test",
                description="Test",
                service_instructions="Use published knowledge",
                handoff_enabled=True,
            )
        )
        session.commit()

    identity_field = "from_user_id" if customer_id.startswith("PE.") else "from"
    contact_field = "user_id" if identity_field == "from_user_id" else "wa_id"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": runtime.channel.phone_number_id
                            },
                            "contacts": [
                                {
                                    contact_field: "15550100888",
                                    "profile": {"username": "wrong_contact"},
                                },
                                {
                                    contact_field: customer_id,
                                    "profile": {"username": username},
                                },
                            ],
                            "messages": [
                                {
                                    "id": "wamid.adviser-alert",
                                    identity_field: customer_id,
                                    "timestamp": str(
                                        int(datetime.now(UTC).timestamp())
                                    ),
                                    "referral": {
                                        "source_type": "ad",
                                        "source_id": "123",
                                    },
                                    "type": "text",
                                    "text": {
                                        "body": "Necesito una web para mi taller. "
                                        "Mi enlace es https://taller.example."
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    parsed_payload = WhatsAppWebhookParser().parse(
        json.dumps(payload).encode(), max_events=10
    )
    with runtime.sessions() as session:
        processor = get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        )
        results = await processor.process(
            parsed_payload,
            public_webhook_id=runtime.channel.public_webhook_id,
            correlation_id=uuid4(),
        )
        assert results[0].status == "processed"
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.status = "ready"
        job.result_ciphertext = cipher().encrypt(
            json.dumps({"reply": "unused", "handoff": True})
        )
        conversation_id = job.conversation_id
        session.commit()

    requests: list[dict[str, Any]] = []

    def send(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if requests[-1]["type"] == "template":
            if outcome == "failed":
                return httpx.Response(
                    400, json={"error": {"message": "test rejection"}}
                )
            if outcome == "unknown":
                raise httpx.ReadTimeout("test lost acknowledgement", request=request)
        return httpx.Response(
            200, json={"messages": [{"id": f"wamid.sent.{len(requests)}"}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http:
        runtime.settings.whatsapp_live_client_mode = "meta"
        runtime.settings.whatsapp_outbound_allowed_recipients = (
            alert_config.recipient,
        )
        meta = MetaWhatsAppCloudApiClient(
            api_version="v26.0", timeout_seconds=1, http_client=http
        )
        monkeypatch.setattr(
            "app.operations.ai_consumer.get_whatsapp_cloud_api_client",
            lambda settings: meta,
        )
        assert await dispatch_one(runtime.service)
        if change_recipient:
            runtime.settings.handoff_alert_scopes = {
                scope: alert_config.model_copy(update={"recipient": "15550100102"})
            }
        assert await dispatch_adviser_alert(runtime.service)
        assert not await dispatch_adviser_alert(runtime.service)

    recipient_field = "to" if identity_field == "from" else "recipient"
    assert requests[0][recipient_field] == customer_id
    assert requests[0]["type"] == "text"
    assert "Te dejo con Alex" in requests[0]["text"]["body"]
    if change_recipient:
        assert len(requests) == 1
    else:
        assert len(requests) == 2
        assert requests[1]["to"] == alert_config.recipient
        assert requests[1]["type"] == "template"
        template = requests[1]["template"]
        assert template["name"] == alert_config.template_name
        assert template["language"] == {"code": "es"}
        parameters = template["components"][0]["parameters"]
        assert [part["text"] for part in parameters] == [
            expected_contact,
            "Necesito una web para mi taller. Mi enlace es [enlace omitido]",
            f"https://luri.example.test/portal?org={runtime.channel.organization_id}"
            f"&conversation={conversation_id}",
        ]
    with runtime.sessions() as session:
        attempts = session.scalars(select(OutboundMessageAttemptModel)).all()
        assert len(attempts) == 2
        alert = next(attempt for attempt in attempts if attempt.notification)
        assert (
            next(attempt for attempt in attempts if not attempt.notification).status
            == "sent"
        )
        if change_recipient:
            assert alert.last_error_code == "ADVISER_ALERT_NOT_AUTHORIZED"
        elif outcome == "failed":
            assert alert.last_error_code == "INVALID_REQUEST"
        elif outcome == "unknown":
            assert alert.last_error_code == "DELIVERY_UNKNOWN"
        else:
            assert alert.status == "sent" and alert.attempt_count == 1
        assert "mi taller" not in cipher().decrypt(alert.message_ciphertext)
        handoff = session.scalars(select(HandoffSessionModel)).one()
        assert handoff.status == "waiting_human"
        reads = HumanHandoffService(
            HumanHandoffRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            allow_all_plan_enforcement(),
        )
        owner = User(
            organization_id=channel.organization_id,
            email="owner@example.test",
            role="organization_owner",
        )
        assert (
            reads.get(
                channel.organization_id, conversation_id, owner
            ).adviser_alert_status
            == outcome
        )
        foreign = owner.model_copy(update={"organization_id": uuid4()})
        with pytest.raises(HandoffForbiddenError):
            reads.get(channel.organization_id, conversation_id, foreign)
        handoff.status = "human_active"
        handoff.version += 1
        session.flush()
        assert (
            reads.get(
                channel.organization_id, conversation_id, owner
            ).adviser_alert_status
            == outcome
        )
        handoff.requested_at = alert.created_at + timedelta(seconds=1)
        session.flush()
        assert (
            reads.get(
                channel.organization_id, conversation_id, owner
            ).adviser_alert_status
            is None
        )
        messages = session.scalars(select(MessageModel)).all()
        assert all(message.outbound_attempt_id != alert.id for message in messages)
        if username:
            inbound = next(
                message for message in messages if message.direction == "inbound"
            )
            assert username not in json.dumps(inbound.metadata_data)
            assert username not in json.dumps(inbound.extra_data)


APPROVED_WEBSITE_GREETING = (
    "Para ayudarte a elegir una web que le sirva a tu negocio, cuéntame un poco. "
    "¿A qué se dedica tu empresa y qué te gustaría lograr con tu página? "
    "Por ejemplo, mostrar tus servicios, recibir consultas por WhatsApp o vender "
    "en línea."
)
KMP_INTRO = "¡Hola! Soy Luri, asistente de Kalivur Marketing Pro. 👋"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "Hola, me interesa la web con branding desde S/250. Mi negocio es…",
            APPROVED_WEBSITE_GREETING,
        ),
        (
            "Hola, quiero cotizar el diseño de una página web para mi negocio.",
            APPROVED_WEBSITE_GREETING,
        ),
        ("¿Cuánto cuesta una página web?", APPROVED_WEBSITE_GREETING),
        ("¿Cuánto cuesta una landing?", APPROVED_WEBSITE_GREETING),
        (
            "Buenas tardes, quisiera un préstamo para mi negocio",
            "Aquí atendemos consultas sobre diseño web para negocios.",
        ),
    ],
)
async def test_website_sales_intake_from_ads_uses_scoped_short_reply(
    runtime: Runtime, content: str, expected: str
) -> None:
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot is not None
        bot.settings = {
            "generative_ai": AIConfig(
                enabled=True,
                qualify_for_proposal=True,
                website_sales_intake=True,
                whatsapp_ads_only=True,
                handoff_adviser_name="Alex",
                conversational_response=ResponseConfig(enabled=True),
            ).model_dump()
        }
        bot.welcome_message = KMP_INTRO
        session.commit()
    await runtime.inbound(text=content, ad_source_id="1500")
    assert await runtime.service.run_once()
    assert not runtime.provider.calls
    assert await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert attempt.status == "sent"
        assert (
            cipher().decrypt(attempt.message_ciphertext) == f"{KMP_INTRO}\n\n{expected}"
        )


async def test_website_first_reply_uses_business_already_shared(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    objective_question = "¿Qué te gustaría lograr con tu página web?"
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot is not None
        bot.welcome_message = KMP_INTRO
        bot.settings = {
            "generative_ai": AIConfig(
                enabled=True,
                qualify_for_proposal=True,
                website_sales_intake=True,
                whatsapp_ads_only=True,
                handoff_adviser_name="Alex",
                needs=[
                    NeedDefinition(
                        key="negocio",
                        question="¿A qué se dedica tu empresa?",
                        attribute="giro",
                    ),
                    NeedDefinition(
                        key="situacion",
                        question="¿Ya tienes una web?",
                        attribute="situacion",
                    ),
                    NeedDefinition(
                        key="objetivo",
                        question=objective_question,
                        attribute="objetivo",
                    ),
                ],
            ).model_dump()
        }
        session.commit()
    original_generate = runtime.provider.generate

    async def generate(
        *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        if stage != "discovery":
            return await original_generate(stage=stage, context=context, schema=schema)
        message = json.loads(context)["history"][-1]
        return Generation(
            data=Discovery(
                new_topic=False,
                needs=[
                    NeedPatch(
                        key="negocio",
                        value="una panadería",
                        message_ref=message["ref"],
                        quote="Tengo una panadería",
                    )
                ],
                search_terms=[],
                handoff_requested=False,
            ).model_dump_json(),
            usage=Usage(input_tokens=50, output_tokens=20, model="gpt-6-luna"),
        )

    monkeypatch.setattr(runtime.provider, "generate", generate)
    await runtime.inbound(
        text="Tengo una panadería y quiero una web.", ad_source_id="1500"
    )
    assert await runtime.service.run_once()
    assert await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert attempt.status == "sent"
        assert (
            cipher().decrypt(attempt.message_ciphertext)
            == f"{KMP_INTRO}\n\n{objective_question}"
        )
        memory = session.scalars(select(AIMemoryModel)).one()
        assert json.loads(cipher().decrypt(memory.ciphertext))["negocio"]["value"] == (
            "una panadería"
        )


@pytest.mark.parametrize("stop", ["none", "reply", "human", "expired"])
async def test_website_reminder_delivery_rules(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    # 21:01 Lima. The nominal first reminder lands outside the allowed hours
    # and the second falls too close to the reprogrammed first reminder.
    greeting = datetime(2040, 5, 1, 2, 1, tzinfo=UTC)
    clock = greeting
    factory = get_whatsapp_live_message_processor

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "FixedClock":
            return cls.fromtimestamp(clock.timestamp(), tz)

    def processor_at_clock(*args: Any, **kwargs: Any) -> Any:
        processor = factory(*args, **kwargs)
        processor._now = lambda: clock
        return processor

    monkeypatch.setattr(ai_consumer, "datetime", FixedClock)
    monkeypatch.setattr(
        ai_consumer, "get_whatsapp_live_message_processor", processor_at_clock
    )
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot is not None
        bot.timezone = "America/Lima"
        bot.welcome_message = KMP_INTRO
        bot.settings = {
            "generative_ai": AIConfig(
                enabled=True,
                website_sales_intake=True,
                website_sales_follow_up=True,
                whatsapp_ads_only=True,
                handoff_adviser_name="Alex",
            ).model_dump()
        }
        session.commit()
    await runtime.inbound(text="¿Cuánto cuesta una landing?", ad_source_id="1500")
    assert await runtime.service.run_once()
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job_id = job.id
        conversation = session.get(ConversationModel, job.conversation_id)
        receipt = session.get(InboundMessageReceiptModel, job.receipt_id)
        assert conversation is not None and receipt is not None
        last_inbound = greeting - timedelta(hours=14) if stop == "expired" else greeting
        conversation.last_inbound_at = last_inbound
        receipt.received_at = last_inbound
        session.commit()
    assert await dispatch_one(runtime.service)
    assert not runtime.provider.calls
    assert not await dispatch_website_reminder(runtime.service)
    clock += timedelta(seconds=2)
    assert await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        current_job = session.get(AIJobModel, job_id)
        assert current_job is not None
        conversation = session.get(ConversationModel, current_job.conversation_id)
        assert conversation is not None and conversation.outbound_message_count == 1
        if stop == "human":
            session.add(
                HandoffSessionModel(
                    conversation_id=current_job.conversation_id,
                    organization_id=current_job.organization_id,
                    bot_id=current_job.bot_id,
                    status="human_active",
                )
            )
            session.commit()
    if stop == "reply":
        await runtime.inbound(
            message_id="test-ai-response", text="Mi negocio es una panadería"
        )

    clock = greeting + timedelta(hours=4)
    assert await dispatch_website_reminder(runtime.service)
    with runtime.sessions() as session:
        first = session.scalar(
            select(OutboundMessageAttemptModel).where(
                OutboundMessageAttemptModel.idempotency_key == reminder_key(job_id, 1)
            )
        )
        assert first is not None
        first_id = first.id
        if stop != "none":
            error = {
                "reply": "REMINDER_NO_LONGER_ELIGIBLE",
                "human": "REMINDER_HUMAN_INTERVENED",
                "expired": "REMINDER_WINDOW_CLOSED",
            }[stop]
            assert first.status == "failed"
            assert first.last_error_code == error
        else:
            assert first.status == "pending"
            assert first.next_attempt_at == datetime(2040, 5, 1, 13, 0)

    if stop != "none":
        clock = greeting + timedelta(hours=12)
        assert await dispatch_website_reminder(runtime.service)
        with runtime.sessions() as session:
            sent = session.scalars(
                select(OutboundMessageAttemptModel).where(
                    OutboundMessageAttemptModel.status == "sent"
                )
            ).all()
            assert len(sent) == 1
        assert not runtime.provider.calls
        if stop == "reply":
            assert await runtime.service.run_once()
            assert runtime.provider.calls
        return

    # A worker delay makes the first send actually occur at 08:20, so the
    # second can only go at 12:20 or later.
    clock = datetime(2040, 5, 1, 13, 20, tzinfo=UTC)
    assert await dispatch_website_reminder(runtime.service)
    clock = greeting + timedelta(hours=12)
    assert await dispatch_website_reminder(runtime.service)
    assert not await dispatch_website_reminder(runtime.service)
    clock = datetime(2040, 5, 1, 17, 20, tzinfo=UTC)
    assert await dispatch_website_reminder(runtime.service)
    assert not await dispatch_website_reminder(runtime.service)
    assert not runtime.provider.calls
    with runtime.sessions() as session:
        first = session.get(OutboundMessageAttemptModel, first_id)
        last = session.scalar(
            select(OutboundMessageAttemptModel).where(
                OutboundMessageAttemptModel.idempotency_key == reminder_key(job_id, 2)
            )
        )
        assert first is not None and last is not None
        assert first.status == last.status == "sent"
        assert first.sent_at is not None and last.sent_at is not None
        assert last.sent_at - first.sent_at == timedelta(hours=4)
        assert cipher().decrypt(first.message_ciphertext) == REMINDER_TEXT[1]
        assert cipher().decrypt(last.message_ciphertext) == REMINDER_TEXT[2]


@pytest.mark.parametrize("model", [None, "gpt-6.1-terra"])
async def test_bot_model_override(runtime: Runtime, model: AIModel | None) -> None:
    terra = FakeProvider()
    runtime.service.alternate_providers = {"gpt-6.1-terra": terra}
    if model is not None:
        with runtime.sessions() as session:
            bot = session.get(BotModel, runtime.channel.bot_id)
            assert bot is not None
            bot.settings = {
                "generative_ai": CONFIG.model_copy(update={"model": model}).model_dump()
            }
            session.commit()

    await runtime.inbound()
    assert await runtime.service.run_once()
    assert runtime.settings.ai_model == "gpt-6-luna"
    assert bool(runtime.provider.calls) is (model is None)
    assert bool(terra.calls) is (model is not None)


async def test_durable_webhook_generation_outbox_idempotency(runtime: Runtime) -> None:
    await runtime.inbound()
    await runtime.inbound()
    assert not runtime.provider.calls
    with runtime.sessions() as session:
        assert len(session.scalars(select(AIJobModel)).all()) == 1
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()
    assert await runtime.service.run_once()
    assert len(runtime.provider.calls) == 2
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready", job.error_code
        memory = session.get(AIMemoryModel, job.conversation_id)
        assert memory and "age" not in memory.ciphertext
        assert json.loads(cipher().decrypt(memory.ciphertext))["age"]["value"] == "5"
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    await runtime.inbound()
    with runtime.sessions() as session:
        attempts = session.scalars(select(OutboundMessageAttemptModel)).all()
        assert len(attempts) == 1
        assert attempts[0].status == "sent"
        assert "Dino" in cipher().decrypt(attempts[0].message_ciphertext)


def set_pilot_recipients(runtime: Runtime, recipients: list[str]) -> None:
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        config = AIConfig.model_validate(bot.settings["generative_ai"]).model_dump()
        config["pilot_recipients"] = recipients
        bot.settings = {**bot.settings, "generative_ai": config}
        session.commit()


async def test_pilot_denied_sender_keeps_history_without_ai_or_legacy_reply(
    runtime: Runtime,
) -> None:
    from app.infrastructure.models.message import MessageModel

    set_pilot_recipients(runtime, [])
    await runtime.inbound()
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        messages = session.scalars(select(MessageModel)).all()
        assert len(messages) == 1 and messages[0].direction == "inbound"
        assert messages[0].text_ciphertext and not messages[0].content
        assert not session.scalars(select(AIJobModel)).all()
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()
    assert not runtime.provider.calls


async def test_pilot_allowed_sender_generates(runtime: Runtime) -> None:
    set_pilot_recipients(runtime, ["51999999999"])
    await runtime.inbound()
    assert await runtime.service.run_once()
    assert len(runtime.provider.calls) == 2
    assert all(
        "pilot_recipients" not in call["config"] for call in runtime.provider.calls
    )


async def test_pilot_revocation_cancels_queued_generation(runtime: Runtime) -> None:
    set_pilot_recipients(runtime, ["51999999999"])
    await runtime.inbound()
    set_pilot_recipients(runtime, [])
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
    assert not runtime.provider.calls


async def test_pilot_revocation_blocks_ready_response(runtime: Runtime) -> None:
    set_pilot_recipients(runtime, ["51999999999"])
    await runtime.inbound()
    assert await runtime.service.run_once()
    set_pilot_recipients(runtime, [])
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status != "sent"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


def test_pilot_contract_and_legacy_hash() -> None:
    import hashlib

    from app.application.generative_ai.policy import config_hash, recipient_allowed

    legacy = CONFIG.model_dump_json(
        exclude={
            "conversational_response",
            "model",
            "pilot_recipients",
            "whatsapp_ads_only",
            "handoff_adviser_name",
            "website_sales_intake",
            "website_sales_follow_up",
        }
    )
    assert config_hash(CONFIG) == hashlib.sha256(legacy.encode()).hexdigest()
    assert config_hash(
        CONFIG.model_copy(update={"model": "gpt-6.1-terra"})
    ) == config_hash(CONFIG)
    assert recipient_allowed(CONFIG, "51999999999")
    assert not recipient_allowed(AIConfig(pilot_recipients=[]), "51999999999")
    for invalid in [["+51999999999"], ["51999999999"] * 2, ["bad"]]:
        with pytest.raises(ValidationError):
            AIConfig(pilot_recipients=invalid)


async def test_no_checked_out_connection_during_provider(runtime: Runtime) -> None:
    await runtime.inbound()
    engine = runtime.sessions.kw["bind"]

    def check() -> None:
        assert engine.pool.checkedout() == 0

    runtime.provider.on_call = check
    await runtime.service.run_once()
    assert len(runtime.provider.calls) == 2


async def test_restart_and_stale_owner_fencing(runtime: Runtime) -> None:
    await runtime.inbound()
    first = runtime.service.claim()
    assert first
    with runtime.sessions() as session:
        job = session.get(AIJobModel, first[0])
        assert job
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    second = runtime.service.claim()
    assert second and second[1] != first[1]
    with pytest.raises(ProviderError, match="LOST_LEASE"):
        runtime.service.snapshot(*first)
    runtime.service.fail(*first, ProviderError("STALE"))
    with runtime.sessions() as session:
        assert session.get(AIJobModel, first[0]).token == second[1]  # type: ignore[union-attr]


async def test_disable_and_newer_message_suppress_old_work(runtime: Runtime) -> None:
    await runtime.inbound()
    await runtime.inbound("test-ai-2")
    await runtime.service.run_once()
    with runtime.sessions() as session:
        jobs = session.scalars(select(AIJobModel).order_by(AIJobModel.created_at)).all()
        assert jobs[0].status == "cancelled"
        assert jobs[1].status == "ready"
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        bot.settings = {"generative_ai": {"enabled": False}}
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_bounded_provider_failures(runtime: Runtime) -> None:
    await runtime.inbound()
    runtime.provider.error = ProviderError("TIMEOUT", True)
    await runtime.service.run_once()
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "retry"
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await runtime.service.run_once()
    assert not await runtime.service.run_once()
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready" and job.attempts == 2
        assert job.error_code == "TIMEOUT"


async def test_unsupported_recommendation_degrades_instead_of_fallback(
    runtime: Runtime,
) -> None:
    with runtime.sessions() as session:
        entry = session.get(KnowledgeEntryModel, runtime.item_id)
        assert entry is not None
        entry.metadata_data = {
            "catalog_item": {
                "name": "Dino",
                "attributes": [
                    {
                        "key": "age",
                        "label": "Edad recomendada",
                        "value": "8 a 10 años",
                        "minimum": 8,
                        "maximum": 10,
                    }
                ],
            }
        }
        session.commit()
    await runtime.inbound()
    assert await runtime.service.run_once()
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready" and job.error_code is None
        reply = json.loads(cipher().decrypt(job.result_ciphertext or ""))["reply"]
    assert reply != FALLBACK
    assert "Dino" not in reply


async def test_unpublished_source_cancels_dispatch(runtime: Runtime) -> None:
    await runtime.inbound()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        source = session.get(KnowledgeEntryModel, runtime.item_id)
        assert source
        source.status = "draft"
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled": True, "tools": ["sql"]},
        {"enabled": True, "base_url": "https://evil.test"},
        {"model": "other"},
        {"daily_jobs": 99999},
    ],
)
def test_settings_cannot_expand_authority(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BotUpdate(settings={"generative_ai": payload})


def test_memory_requires_evidence_and_corrections_keep_history_separate() -> None:
    discovery = Discovery(
        new_topic=False,
        needs=[NeedPatch(key="age", value="8", quote="tiene 8 años", message_ref="m2")],
        search_terms=[],
        handoff_requested=False,
    )
    original = {"age": {"value": "5"}}
    memory = apply_discovery(discovery, CONFIG, original, {"m2": "Ahora tiene 8 años"})
    assert original["age"]["value"] == "5"
    assert memory["age"]["value"] == "8"
    assert memory["age"]["status"] != "confirmed"
    with pytest.raises(ProviderError):
        apply_discovery(discovery, CONFIG, original, {"m2": "sin edad"})


def test_recommendation_rejects_unknown_item() -> None:
    result = AdviserResult.model_validate(
        {
            "tone": "options",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [
                {
                    "item_ref": "other-tenant",
                    "matches": [{"need_key": "age", "attribute_key": "age"}],
                }
            ],
            "knowledge": [],
        }
    )
    with pytest.raises(ProviderError, match="UNKNOWN_ITEM"):
        render(result, CONFIG, {"age": {"value": "5"}}, {})


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-terra"])
async def test_openai_wire_is_strict_and_no_tools_or_storage(model: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert payload["model"] == model
        assert payload["tools"] == [] and payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": model,
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
            },
        )

    provider = OpenAIProvider(
        SecretStr("fake-test-key"), 2, 1000, httpx.MockTransport(respond), model=model
    )
    result = await provider.generate(stage="discovery", context="{}", schema=Discovery)
    assert result.usage.input_tokens == 10


@pytest.mark.parametrize(
    "status,retryable", [(401, False), (403, False), (429, True), (500, True)]
)
async def test_provider_errors_are_sanitized(status: int, retryable: bool) -> None:
    provider = OpenAIProvider(
        SecretStr("fake-key"),
        2,
        1000,
        httpx.MockTransport(
            lambda request: httpx.Response(status, text="private body")
        ),
        model="gpt-6-luna",
    )
    with pytest.raises(ProviderError) as failure:
        await provider.generate(stage="discovery", context="{}", schema=Discovery)
    assert failure.value.retryable == retryable
    assert "private" not in str(failure.value)


async def test_cross_tenant_and_other_bot_sources_never_retrieved(
    runtime: Runtime,
) -> None:
    await runtime.inbound()
    with runtime.sessions() as session:
        for org, bot in [
            (uuid4(), uuid4()),
            (runtime.channel.organization_id, uuid4()),
        ]:
            session.add(
                KnowledgeEntryModel(
                    organization_id=org,
                    bot_id=bot,
                    title="Dinosaurio secreto",
                    content="private-other-bot",
                    status="published",
                    created_by_user_id=uuid4(),
                    metadata_data={},
                )
            )
        session.commit()
    claim = runtime.service.claim()
    assert claim
    sources = runtime.service.retrieve(*claim, ["dinosaurio"])
    assert list(sources) == [str(runtime.item_id)]


async def test_handoff_during_generation_suppresses_reply(runtime: Runtime) -> None:
    from app.infrastructure.models.human_handoff import HandoffSessionModel

    await runtime.inbound()

    def takeover() -> None:
        with runtime.sessions() as session:
            job = session.scalars(select(AIJobModel)).one()
            session.add(
                HandoffSessionModel(
                    organization_id=job.organization_id,
                    bot_id=job.bot_id,
                    conversation_id=job.conversation_id,
                    status="human_active",
                )
            )
            session.commit()
        runtime.provider.on_call = None

    runtime.provider.on_call = takeover
    await runtime.service.run_once()
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_expired_delivery_is_unknown_not_resent(runtime: Runtime) -> None:
    await runtime.inbound()
    await runtime.service.run_once()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        attempt = session.get(OutboundMessageAttemptModel, job.outbound_id)
        assert attempt
        attempt.status = "pending"
        attempt.delivery_token = uuid4()
        attempt.delivery_started_at = datetime.now(UTC) - timedelta(minutes=10)
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "delivery_unknown"
        assert len(session.scalars(select(OutboundMessageAttemptModel)).all()) == 1


@pytest.mark.parametrize(
    "attributes",
    [
        [],
        [
            {
                "key": "age",
                "label": "Edad",
                "value": "8 a 10",
                "minimum": 8,
                "maximum": 10,
            }
        ],
    ],
)
def test_missing_or_incompatible_catalog_attributes_rejected(
    attributes: list[dict[str, Any]],
) -> None:
    result = AdviserResult.model_validate(
        {
            "tone": "options",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [
                {
                    "item_ref": "p",
                    "matches": [{"need_key": "age", "attribute_key": "age"}],
                }
            ],
            "knowledge": [],
        }
    )
    with pytest.raises(ProviderError, match="MISSING_OR_INCOMPATIBLE"):
        render(
            result,
            CONFIG,
            {"age": {"value": "5"}},
            {
                "p": {
                    "version": "1",
                    "catalog": {"name": "Product", "attributes": attributes},
                }
            },
        )


def test_known_need_is_not_asked_again() -> None:
    result = AdviserResult(
        tone="clarify",
        question_key="age",
        handoff_requested=False,
        recommendations=[],
        knowledge=[],
    )
    with pytest.raises(ProviderError, match="REPEATED"):
        render(result, CONFIG, {"age": {"value": "5"}}, {})


def test_salvage_drops_only_unsupported_parts() -> None:
    catalog = {
        "name": "Dino",
        "attributes": [
            {
                "key": "age",
                "label": "Edad",
                "value": "4 a 7",
                "minimum": 4,
                "maximum": 7,
            }
        ],
    }
    too_old = {
        "name": "Robot",
        "attributes": [
            {
                "key": "age",
                "label": "Edad",
                "value": "8 a 10",
                "minimum": 8,
                "maximum": 10,
            }
        ],
    }
    sources: dict[str, dict[str, Any]] = {
        "ok": {"version": "1", "catalog": catalog},
        "bad": {"version": "1", "catalog": too_old},
        "k": {"version": "1", "catalog": None, "content": "Envíos en Lima."},
    }
    match = [{"need_key": "age", "attribute_key": "age"}]
    result = AdviserResult.model_validate(
        {
            "tone": "options",
            "question_key": "age",
            "handoff_requested": False,
            "recommendations": [
                {"item_ref": "ok", "matches": match},
                {"item_ref": "bad", "matches": match},
                {"item_ref": "missing", "matches": match},
            ],
            "knowledge": [
                {"source_ref": "k", "quote": "Envíos en Lima."},
                {"source_ref": "k", "quote": "Envíos gratis en Lima."},
            ],
        }
    )
    memory = {"age": {"value": "5"}}
    salvaged = salvage(result, CONFIG, memory, sources)
    assert salvaged.question_key is None
    assert [r.item_ref for r in salvaged.recommendations] == ["ok"]
    assert [q.quote for q in salvaged.knowledge] == ["Envíos en Lima."]
    text, used = render(salvaged, CONFIG, memory, sources)
    assert "Dino" in text and "Robot" not in text
    assert set(used) == {"ok", "k"}


def test_salvage_falls_back_to_pending_question_not_generic_reply() -> None:
    result = AdviserResult.model_validate(
        {
            "tone": "options",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [
                {
                    "item_ref": "p",
                    "matches": [{"need_key": "age", "attribute_key": "age"}],
                }
            ],
            "knowledge": [],
        }
    )
    salvaged = salvage(result, CONFIG, {}, {})
    assert salvaged.recommendations == []
    text, _ = render(salvaged, CONFIG, {}, {})
    assert text == "¿Qué edad tiene?"
    assert text != FALLBACK


def test_number_substring_is_not_evidence() -> None:
    discovery = Discovery(
        new_topic=False,
        needs=[NeedPatch(key="age", value="5", message_ref="m", quote="tiene 15 años")],
        search_terms=[],
        handoff_requested=False,
    )
    with pytest.raises(ProviderError, match="UNSUPPORTED_NUMERIC"):
        apply_discovery(discovery, CONFIG, {}, {"m": "tiene 15 años"})


def test_knowledge_quote_cannot_drop_negation() -> None:
    result = AdviserResult.model_validate(
        {
            "tone": "understood",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [],
            "knowledge": [{"source_ref": "k", "quote": "aceptamos devoluciones"}],
        }
    )
    with pytest.raises(ProviderError, match="UNSUPPORTED_KNOWLEDGE"):
        render(
            result,
            CONFIG,
            {},
            {
                "k": {
                    "content": "No aceptamos devoluciones",
                    "version": "1",
                    "catalog": None,
                }
            },
        )


async def test_metrics_are_content_free_and_report_usage(runtime: Runtime) -> None:
    from app.operations.ai_metrics import snapshot

    await runtime.inbound()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        metrics = snapshot(session)
    assert metrics["input_tokens"] == 100
    assert metrics["output_tokens"] == 40
    assert metrics["generation_seconds"]["count"] == 2
    assert "sobrino" not in json.dumps(metrics)


async def test_daily_limit_prevents_provider_call(runtime: Runtime) -> None:
    runtime.settings.ai_daily_call_limit = 1
    await runtime.inbound()
    await runtime.service.run_once()
    assert len(runtime.provider.calls) == 1
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.error_code == "DAILY_LIMIT"
        assert job.status == "ready"


async def test_missing_key_never_makes_http_request() -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not use HTTP")

    provider = OpenAIProvider(
        SecretStr(""), 2, 1000, httpx.MockTransport(forbidden), model="gpt-6-luna"
    )
    with pytest.raises(ProviderError, match="MISSING_PROVIDER_KEY"):
        await provider.generate(stage="discovery", context="{}", schema=Discovery)


def test_ai_model_defaults_to_luna_and_rejects_unlisted_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOTWA_AI_MODEL", raising=False)
    assert Settings(_env_file=None).ai_model == "gpt-6-luna"
    monkeypatch.setenv("BOTWA_AI_MODEL", "gpt-6.1-terra")
    assert Settings(_env_file=None).ai_model == "gpt-6.1-terra"
    monkeypatch.setenv("BOTWA_AI_MODEL", "gpt-6-astra")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_automation_lane_runs_while_ai_is_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Event

    from app.operations import automation_worker

    entered, released = Event(), Event()

    def slow_ai(stop_event: Event, *, once: bool = False) -> None:
        entered.set()
        assert released.wait(5), "automation lane was blocked by AI"

    def automate(batch_size: int) -> int:
        assert entered.wait(5)
        released.set()
        return 0

    monkeypatch.setattr("app.operations.ai_consumer.run_ai_lane", slow_ai)
    monkeypatch.setattr(automation_worker, "run_batch", automate)
    monkeypatch.setattr(
        automation_worker, "install_shutdown_handlers", lambda event: None
    )
    monkeypatch.setattr("sys.argv", ["automation_worker", "--once"])
    automation_worker.main()
    assert released.is_set()


async def test_bot_settings_update_cancels_jobs_immediately(runtime: Runtime) -> None:
    from app.application.bots.service import BotService
    from app.domain.user.contracts import User
    from app.infrastructure.repositories.audit_repository import (
        SqlAlchemyAuditRepository,
    )
    from app.infrastructure.repositories.bot_repository import BotRepository
    from app.infrastructure.repositories.organization_repository import (
        OrganizationRepository,
    )

    from tests.plan_support import allow_all_plan_enforcement

    await runtime.inbound()
    with runtime.sessions() as session:
        service = BotService(
            BotRepository(session),
            OrganizationRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            allow_all_plan_enforcement(),
        )
        service.update(
            runtime.channel.bot_id,
            BotUpdate(settings={"generative_ai": {"enabled": False}}),
            User(
                id=runtime.channel.created_by_user_id,
                organization_id=runtime.channel.organization_id,
                email="owner@example.test",
                role="organization_owner",
            ),
        )
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"


async def test_new_input_between_enqueue_and_send_is_suppressed(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor

    await runtime.inbound()
    await runtime.service.run_once()

    async def defer(*args: Any, **kwargs: Any) -> bool:
        return False

    with monkeypatch.context() as patch:
        patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", defer)
        await dispatch_one(runtime.service)
    await runtime.inbound("new-correction-before-send")
    with runtime.sessions() as session:
        attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
        processor = get_whatsapp_live_message_processor(
            session, cipher(), FakeWhatsAppCloudApiClient(), runtime.settings
        )
        assert not await processor.retry_attempt(attempt.id)
        assert attempt.status == "failed"
        assert attempt.last_error_code == "AI_POLICY_CHANGED"


@pytest.mark.parametrize(
    ("adviser_name", "takeover_before_retry"),
    [(None, False), ("Alex", False), ("Alex", True)],
)
async def test_assistant_requests_real_handoff_without_impersonation(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    adviser_name: str | None,
    takeover_before_retry: bool,
) -> None:
    from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
    from app.infrastructure.models.business_configuration import (
        BusinessConfigurationModel,
    )
    from app.infrastructure.models.human_handoff import HandoffSessionModel

    from tests.plan_support import allow_all_plan_enforcement

    monkeypatch.setattr(
        "app.operations.ai_consumer.PlanEnforcementService",
        lambda repository: allow_all_plan_enforcement(),
    )
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot is not None
        bot.settings = {
            "generative_ai": CONFIG.model_copy(
                update={"handoff_adviser_name": adviser_name}
            ).model_dump()
        }
        bot.welcome_message = "Hola, soy Luri, tu asistente virtual."
        session.commit()
    await runtime.inbound()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.result_ciphertext = cipher().encrypt(
            json.dumps({"reply": "unused", "handoff": True})
        )
        session.add(
            BusinessConfigurationModel(
                bot_id=job.bot_id,
                business_name="Test",
                description="Test",
                service_instructions="Use published knowledge",
                handoff_enabled=True,
            )
        )
        session.commit()
    if takeover_before_retry:

        async def defer_delivery(*args: Any, **kwargs: Any) -> bool:
            return False

        with monkeypatch.context() as patch:
            patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", defer_delivery)
            await dispatch_one(runtime.service)
        with runtime.sessions() as session:
            handoff = session.scalars(select(HandoffSessionModel)).one()
            handoff.status = "human_active"
            handoff.version += 1
            session.commit()
    else:
        await dispatch_one(runtime.service)
    if adviser_name:
        with runtime.sessions() as session:
            job = session.scalars(select(AIJobModel)).one()
            job.available_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        await dispatch_one(runtime.service)
    if takeover_before_retry:
        with runtime.sessions() as session:
            attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
            assert attempt.status == "failed" and attempt.attempt_count == 0
        return
    assert not await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "handoff"
        assert (
            session.scalars(select(HandoffSessionModel)).one().status == "waiting_human"
        )
        attempts = session.scalars(select(OutboundMessageAttemptModel)).all()
        if adviser_name:
            assert len(attempts) == 1
            attempt = attempts[0]
            assert attempt.status == "sent" and attempt.attempt_count == 1
            reply = cipher().decrypt(attempt.message_ciphertext)
            assert reply.startswith("Hola, soy Luri, tu asistente virtual.\n\n")
            assert "Te dejo con Alex" in reply
        else:
            assert not attempts


async def test_daily_limit_hands_off_instead_of_generic_fallback(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.infrastructure.models.business_configuration import (
        BusinessConfigurationModel,
    )
    from app.infrastructure.models.human_handoff import HandoffSessionModel

    from tests.plan_support import allow_all_plan_enforcement

    monkeypatch.setattr(
        "app.operations.ai_consumer.PlanEnforcementService",
        lambda repository: allow_all_plan_enforcement(),
    )
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot is not None
        bot.settings = {
            "generative_ai": CONFIG.model_copy(
                update={"handoff_adviser_name": "Alex"}
            ).model_dump()
        }
        session.add(
            BusinessConfigurationModel(
                bot_id=bot.id,
                business_name="Test",
                description="Test",
                service_instructions="Use published knowledge",
                handoff_enabled=True,
            )
        )
        session.commit()
    runtime.settings.ai_daily_call_limit = 1
    await runtime.inbound()
    await runtime.service.run_once()
    assert len(runtime.provider.calls) == 1
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready" and job.error_code == "DAILY_LIMIT"
        result = json.loads(cipher().decrypt(job.result_ciphertext or ""))
        assert result == {"reply": "", "handoff": True}
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "handoff"
        assert (
            session.scalars(select(HandoffSessionModel)).one().status == "waiting_human"
        )
        attempt = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert attempt.status == "sent"
        reply = cipher().decrypt(attempt.message_ciphertext)
    assert "Te dejo con Alex" in reply
    assert FALLBACK not in reply
