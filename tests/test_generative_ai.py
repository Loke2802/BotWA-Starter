import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.generative_ai.service import AIService
from app.application.generative_ai.validation import apply_discovery, render
from app.domain.bot.contracts import BotUpdate
from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    Discovery,
    Generation,
    NeedDefinition,
    NeedPatch,
    ProviderError,
    Usage,
)
from app.infrastructure.database import Base
from app.infrastructure.generative_ai.openai_provider import OpenAIProvider
from app.infrastructure.models.ai_generation import AIJobModel, AIMemoryModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from app.operations.ai_consumer import dispatch_one
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
            usage=Usage(input_tokens=50, output_tokens=20, model="gpt-5.6-luna"),
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

    async def inbound(self, message_id: str = "test-ai-1") -> None:
        with self.sessions() as session:
            payload = parsed(self.channel.phone_number_id, message_id)
            payload = payload.model_copy(
                update={
                    "messages": (
                        payload.messages[0].model_copy(
                            update={
                                "text": "Mi sobrino tiene 5 años y quiere un dinosaurio"
                            }
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


async def test_openai_wire_is_strict_and_no_tools_or_storage() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert payload["model"] == "gpt-5.6-luna"
        assert payload["tools"] == [] and payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gpt-5.6-luna",
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
        SecretStr("fake-test-key"), 2, 1000, httpx.MockTransport(respond)
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

    provider = OpenAIProvider(SecretStr(""), 2, 1000, httpx.MockTransport(forbidden))
    with pytest.raises(ProviderError, match="MISSING_PROVIDER_KEY"):
        await provider.generate(stage="discovery", context="{}", schema=Discovery)


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


async def test_assistant_requests_real_handoff_without_impersonation(
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
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "handoff"
        assert (
            session.scalars(select(HandoffSessionModel)).one().status == "waiting_human"
        )
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()
