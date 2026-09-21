"""Synthetic contracts and durable stages; never calls a paid provider."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.application.generative_ai import response_pipeline
from app.application.generative_ai.response_context import build_context
from app.application.generative_ai.response_validation import (
    digest,
    validate_draft,
    validate_review,
)
from app.domain.generative_ai.contracts import (
    AdviserResult,
    Generation,
    ProviderError,
    Usage,
)
from app.domain.generative_ai.response_contracts import (
    ConversationalDraft,
    SemanticReview,
)
from app.infrastructure.models.ai_generation import (
    AIAttemptModel,
    AIJobModel,
    AIMemoryModel,
    AIResponseCheckpointModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.operations.ai_consumer import dispatch_one
from pydantic import BaseModel
from sqlalchemy import select

from tests.test_generative_ai import CONFIG, FakeProvider, Runtime, runtime
from tests.test_whatsapp_live_processor_repository import cipher

__all__ = ["runtime"]


def segment(**overrides: Any) -> dict[str, Any]:
    return dict(
        {
            "id": "seg_a",
            "kind": "acknowledgement",
            "text": "Gracias por contarme lo que buscas.",
            "claim_refs": [],
            "need_refs": [],
            "question_ref": None,
            "next_step_ref": None,
            "uncertainty_ref": None,
        },
        **overrides,
    )


class ResponseProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.stages: list[str] = []
        self.reject = False
        self.hook: Any = None

    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        self.stages.append(stage)
        if self.hook:
            self.hook(stage)
        if stage in {"discovery", "adviser"}:
            return await super().generate(stage=stage, context=context, schema=schema)
        data = json.loads(context)
        self.calls.append(data)
        if stage == "conversational_render":
            claim = data["authorized_claims"][0]
            clause = claim["required_clause_refs"][0]
            response = {
                "schema_version": "1",
                "context_id": data["context_id"],
                "segments": [
                    segment(
                        text="Por lo que me cuentas, esta opción podría encajar.",
                        claim_refs=[claim["id"]],
                        need_refs=claim["need_refs"],
                    ),
                    segment(
                        id="seg_b",
                        kind="recommendation",
                        text="{{clause:" + clause + "}}",
                        claim_refs=[claim["id"]],
                    ),
                ],
            }
        else:
            response = {
                "schema_version": "1",
                "context_id": data["context"]["context_id"],
                "draft_digest": data["draft_digest"],
                "approved": not self.reject,
                "segments": [
                    {
                        "segment_id": s["id"],
                        "approved": not self.reject,
                        "reason_code": "UNSUPPORTED_CLAIM" if self.reject else "OK",
                        "unsupported_claim_refs": [],
                    }
                    for s in data["draft"]["segments"]
                ],
            }
        return Generation(
            data=json.dumps(response),
            usage=Usage(input_tokens=30, output_tokens=20, model="gpt-5.6-luna"),
        )


def enable(runtime: Runtime) -> ResponseProvider:
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        config = CONFIG.model_dump()
        config["conversational_response"] = {"enabled": True}
        bot.settings = {"generative_ai": config}
        session.commit()
    provider = ResponseProvider()
    runtime.service.provider = provider
    return provider


async def test_complete_response_and_single_outbox(runtime: Runtime) -> None:
    provider = enable(runtime)
    await runtime.inbound()
    engine = runtime.sessions.kw["bind"]
    provider.hook = lambda _: assert_no_connection(engine)
    assert await runtime.service.run_once()
    assert provider.stages == [
        "discovery",
        "adviser",
        "conversational_render",
        "semantic_review",
    ]
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        job = session.get(AIJobModel, cp.job_id)
        assert job and job.status == "ready", job.error_code if job else None
        assert cp.outcome == "approved", cp.reason_code
        assert cp.committed_revision == 1
        assert "Dino" not in (cp.ciphertext or "")
        assert len(session.scalars(select(AIAttemptModel)).all()) == 4
    await dispatch_one(runtime.service)
    await runtime.inbound()
    with runtime.sessions() as session:
        rows = session.scalars(select(OutboundMessageAttemptModel)).all()
        assert len(rows) == 1
        assert rows[0].status == "sent"
        assert "{{" not in cipher().decrypt(rows[0].message_ciphertext)


def assert_no_connection(engine: Any) -> None:
    assert engine.pool.checkedout() == 0


async def test_four_long_calls_keep_their_lease(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.application.generative_ai import service as service_module

    provider = enable(runtime)
    runtime.service.settings = runtime.settings.model_copy(
        update={"ai_timeout_seconds": 60}
    )
    await runtime.inbound()
    start = datetime.now(UTC)
    elapsed = [0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "Clock":
            return cls.fromtimestamp(
                (start + timedelta(seconds=elapsed[0])).timestamp(), UTC
            )

    monkeypatch.setattr(service_module, "datetime", Clock)
    provider.hook = lambda _: elapsed.__setitem__(0, elapsed[0] + 60)
    await runtime.service.run_once()
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "ready"
        assert (
            session.scalars(select(AIResponseCheckpointModel)).one().outcome
            == "approved"
        )
    assert elapsed[0] == 240


async def test_handoff_during_semantic_review_cancels(runtime: Runtime) -> None:
    from app.infrastructure.models.human_handoff import HandoffSessionModel

    provider = enable(runtime)
    await runtime.inbound()

    def takeover(stage: str) -> None:
        if stage != "semantic_review":
            return
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

    provider.hook = takeover
    await runtime.service.run_once()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert not session.scalars(select(OutboundMessageAttemptModel)).all()


async def test_other_tenant_or_bot_never_enters_response_context(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = Runtime(runtime.sessions, monkeypatch)
    with runtime.sessions() as session:
        source = session.get(KnowledgeEntryModel, other.item_id)
        assert source
        source.metadata_data = {
            "catalog_item": {"name": "SECRET-OTHER-TENANT", "attributes": []}
        }
        session.commit()
    provider = enable(runtime)
    await runtime.inbound()
    await runtime.service.run_once()
    assert len(provider.stages) == 4
    assert "SECRET-OTHER-TENANT" not in json.dumps(provider.calls)
    assert str(other.item_id) not in json.dumps(provider.calls)


async def test_stale_after_outbox_creation_is_suppressed(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_generative_ai import (
        test_new_input_between_enqueue_and_send_is_suppressed as check,
    )

    enable(runtime)
    await check(runtime, monkeypatch)


async def test_remote_unknown_result_falls_back_without_repeating_render(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = enable(runtime)
    await runtime.inbound()
    original = response_pipeline.save

    class ProcessStopped(BaseException):
        pass

    def stop(*args: Any, **kwargs: Any) -> None:
        if args[-1] == "conversational_render_done":
            raise ProcessStopped()
        original(*args, **kwargs)

    monkeypatch.setattr(response_pipeline, "save", stop)
    with pytest.raises(ProcessStopped):
        await runtime.service.run_once()
    monkeypatch.setattr(response_pipeline, "save", original)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await runtime.service.run_once()
    assert provider.stages == ["discovery", "adviser", "conversational_render"]
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == "fallback" and cp.reason_code == "REMOTE_OUTCOME_UNKNOWN"
        assert not session.scalars(
            select(AIAttemptModel).where(AIAttemptModel.result == "reserved")
        ).all()


@pytest.mark.parametrize("limit", [2, 3])
async def test_reserves_both_calls_or_falls_back_before_render(
    runtime: Runtime, limit: int
) -> None:
    provider = enable(runtime)
    runtime.service.settings = runtime.settings.model_copy(
        update={"ai_daily_call_limit": limit}
    )
    await runtime.inbound()
    await runtime.service.run_once()
    assert provider.stages == ["discovery", "adviser"]
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == "fallback" and cp.reason_code == "DAILY_LIMIT"
        job = session.get(AIJobModel, cp.job_id)
        assert job and "Estas opciones" in cipher().decrypt(job.result_ciphertext or "")


async def test_semantic_rejection_uses_base_without_loop(runtime: Runtime) -> None:
    provider = enable(runtime)
    provider.reject = True
    await runtime.inbound()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == "fallback"
        assert cp.reason_code == "REVIEW_UNSUPPORTED_CLAIM"
        job = session.get(AIJobModel, cp.job_id)
        assert job and "Estas opciones" in cipher().decrypt(job.result_ciphertext or "")
    assert len(provider.stages) == 4


@pytest.mark.parametrize("failed_stage", ["conversational_render", "semantic_review"])
async def test_new_stage_timeout_falls_back_without_repair(
    runtime: Runtime, failed_stage: str
) -> None:
    provider = enable(runtime)
    await runtime.inbound()

    def timeout(stage: str) -> None:
        if stage == failed_stage:
            raise ProviderError("TIMEOUT", True)

    provider.hook = timeout
    await runtime.service.run_once()
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == "fallback" and cp.reason_code == "TIMEOUT"
        assert session.scalars(select(AIJobModel)).one().status == "ready"
        assert not session.scalars(
            select(AIAttemptModel).where(AIAttemptModel.result == "reserved")
        ).all()
    assert provider.stages.count(failed_stage) == 1


@pytest.mark.parametrize(
    "stage",
    [
        "discovery_done",
        "memory_applied",
        "adviser_done",
        "conversational_render_done",
        "semantic_review_done",
    ],
)
async def test_restart_reuses_completed_stages(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    provider = enable(runtime)
    await runtime.inbound()
    original = response_pipeline.save

    class ProcessStopped(BaseException):
        pass

    def stop(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        if args[-1] == stage:
            raise ProcessStopped()

    monkeypatch.setattr(response_pipeline, "save", stop)
    with pytest.raises(ProcessStopped):
        await runtime.service.run_once()
    monkeypatch.setattr(response_pipeline, "save", original)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await runtime.service.run_once()
    assert provider.stages == [
        "discovery",
        "adviser",
        "conversational_render",
        "semantic_review",
    ]
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready", job.error_code
        assert session.scalars(select(AIMemoryModel)).one().revision == 1
        assert (
            session.scalars(select(AIResponseCheckpointModel)).one().resumed_from
            == stage
        )
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert len(session.scalars(select(OutboundMessageAttemptModel)).all()) == 1


@pytest.mark.parametrize("change", ["memory", "source", "flag", "input"])
async def test_approved_response_is_rechecked_before_send(
    runtime: Runtime, change: str
) -> None:
    enable(runtime)
    await runtime.inbound()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        if change == "memory":
            memory = session.scalars(select(AIMemoryModel)).one()
            memory.revision += 1
        elif change == "source":
            source = session.get(KnowledgeEntryModel, runtime.item_id)
            assert source
            source.status = "draft"
        elif change == "flag":
            bot = session.get(BotModel, runtime.channel.bot_id)
            assert bot
            bot.settings = {"generative_ai": CONFIG.model_dump()}
        session.commit()
    if change == "input":
        await runtime.inbound("newer-input")
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        rows = session.scalars(select(OutboundMessageAttemptModel)).all()
        if change == "flag":
            assert len(rows) == 1
            assert "Estas opciones" in cipher().decrypt(rows[0].message_ciphertext)
        else:
            assert not rows


async def test_lease_accounts_for_enabled_stages(runtime: Runtime) -> None:
    enable(runtime)
    await runtime.inbound()
    identity = runtime.service.claim()
    assert identity
    with runtime.sessions() as session:
        job = session.get(AIJobModel, identity[0])
        assert job and job.lease_until and job.started_at
        duration = (job.lease_until - job.started_at).total_seconds()
        assert duration == 4 * (runtime.settings.ai_timeout_seconds + 15) + 30


async def test_flag_off_then_on_does_not_resurrect_approved_draft(
    runtime: Runtime,
) -> None:
    from app.application.bots.service import BotService
    from app.domain.bot.contracts import BotUpdate
    from app.domain.user.contracts import User
    from app.infrastructure.repositories.audit_repository import (
        SqlAlchemyAuditRepository,
    )
    from app.infrastructure.repositories.bot_repository import BotRepository
    from app.infrastructure.repositories.organization_repository import (
        OrganizationRepository,
    )

    from tests.plan_support import allow_all_plan_enforcement

    enable(runtime)
    await runtime.inbound()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        service = BotService(
            BotRepository(session),
            OrganizationRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            allow_all_plan_enforcement(),
        )
        for enabled in (False, True):
            config = CONFIG.model_dump()
            config["conversational_response"] = {"enabled": enabled}
            service.update(
                runtime.channel.bot_id,
                BotUpdate(settings={"generative_ai": config}),
                User(
                    id=runtime.channel.created_by_user_id,
                    organization_id=runtime.channel.organization_id,
                    email="owner@example.test",
                    role="organization_owner",
                ),
            )
        assert session.scalars(select(AIJobModel)).one().status == "ready"
        assert session.scalars(select(AIResponseCheckpointModel)).one().response_revoked
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        outbound = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert outbound.status == "sent"
        assert "Estas opciones" in cipher().decrypt(outbound.message_ciphertext)


def synthetic_context() -> Any:
    result = AdviserResult.model_validate(
        {
            "tone": "options",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [
                {
                    "item_ref": "source",
                    "matches": [{"need_key": "age", "attribute_key": "age"}],
                }
            ],
            "knowledge": [],
        }
    )
    return build_context(
        "ctx",
        result,
        CONFIG,
        {
            "age": {
                "value": "5",
                "message_ref": "customer-message",
                "status": "evidence_backed",
            }
        },
        {
            "source": {
                "version": "v1",
                "catalog": {
                    "name": "Dino",
                    "attributes": [
                        {
                            "key": "age",
                            "label": "Edad",
                            "value": "4 a 7 años",
                            "minimum": 4,
                            "maximum": 7,
                        }
                    ],
                },
            }
        },
    )


@pytest.mark.parametrize(
    "text,code",
    [
        ("{{value:invented}}", "INVALID_PLACEHOLDER"),
        ("{{value:need_age}}{{value:need_age}}", "DUPLICATE_PLACEHOLDER"),
        ("Tiene 5 años", "UNAUTHORIZED_LITERAL"),
        ("{{value:need_age.__class__}}", "UNAUTHORIZED_LITERAL"),
        ("Oferta https://example.com", "UNAUTHORIZED_LITERAL"),
    ],
)
def test_placeholders_reject_manipulation(text: str, code: str) -> None:
    context = synthetic_context()
    draft = ConversationalDraft.model_validate(
        {
            "schema_version": "1",
            "context_id": "ctx",
            "segments": [segment(text=text, need_refs=["need_age"])],
        }
    )
    with pytest.raises(ProviderError, match=code):
        validate_draft(context, draft, 3500)


def test_canonical_clause_cannot_be_negated_or_omitted() -> None:
    context = synthetic_context()
    claim = context.authorized_claims[0]
    for text in ["No {{clause:product_0_age}}", "Este producto es perfecto."]:
        draft = ConversationalDraft.model_validate(
            {
                "schema_version": "1",
                "context_id": "ctx",
                "segments": [segment(text=text, claim_refs=[claim.id])],
            }
        )
        with pytest.raises(ProviderError):
            validate_draft(context, draft, 3500)


def test_review_must_cover_every_segment_and_exact_text() -> None:
    context = synthetic_context()
    draft = ConversationalDraft.model_validate(
        {"schema_version": "1", "context_id": "ctx", "segments": [segment()]}
    )
    text = validate_draft(context, draft, 3500)
    review = SemanticReview.model_validate(
        {
            "schema_version": "1",
            "context_id": "ctx",
            "draft_digest": digest(text),
            "approved": True,
            "segments": [
                {
                    "segment_id": "other_segment",
                    "approved": True,
                    "reason_code": "OK",
                    "unsupported_claim_refs": [],
                }
            ],
        }
    )
    with pytest.raises(ProviderError, match="INVALID_REVIEW"):
        validate_review(context, draft, text, review)


def test_policy_clause_has_a_resolvable_reference_and_keeps_negation() -> None:
    policy = "No se realizan entregas fuera de la ciudad."
    result = AdviserResult.model_validate(
        {
            "tone": "unknown",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [],
            "knowledge": [{"source_ref": "policy", "quote": policy}],
        }
    )
    context = build_context(
        "ctx",
        result,
        CONFIG,
        {},
        {"policy": {"version": "v1", "catalog": None, "content": policy}},
    )
    fact = context.business_facts[0]
    assert fact.value_ref is None
    assert fact.clause_ref and context.canonical_clauses[fact.clause_ref] == policy
    draft = ConversationalDraft.model_validate(
        {
            "schema_version": "1",
            "context_id": "ctx",
            "segments": [
                segment(text="{{clause:knowledge_0}}", claim_refs=["claim_knowledge_0"])
            ],
        }
    )
    assert validate_draft(context, draft, 3500) == policy


@pytest.mark.parametrize(
    "overrides",
    [
        {"claim_refs": ["invented_claim"]},
        {"question_ref": "question_age", "kind": "question"},
        {"kind": "comparison", "claim_refs": ["claim_product_0_age"]},
        {"need_refs": ["unknown_need"]},
        {"next_step_ref": "execute_payment"},
    ],
)
def test_references_cannot_expand_authority(overrides: dict[str, Any]) -> None:
    context = synthetic_context()
    draft = ConversationalDraft.model_validate(
        {"schema_version": "1", "context_id": "ctx", "segments": [segment(**overrides)]}
    )
    with pytest.raises(ProviderError):
        validate_draft(context, draft, 3500)


async def test_flag_off_keeps_pr44_reply_and_call_count(runtime: Runtime) -> None:
    await runtime.inbound()
    await runtime.service.run_once()
    assert len(runtime.provider.calls) == 2
    with runtime.sessions() as session:
        assert not session.scalars(select(AIResponseCheckpointModel)).all()
        job = session.scalars(select(AIJobModel)).one()
        assert json.loads(cipher().decrypt(job.result_ciphertext or ""))["reply"] == (
            "Estas opciones podrían encajar con lo que buscas:\n\n"
            "Dino: coincide con lo que buscas. Edad recomendada: 4 a 7 años."
        )


@pytest.mark.parametrize("boundary", ["before_outbox", "after_outbox"])
async def test_restart_around_outbox_does_not_duplicate(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor

    provider = enable(runtime)
    await runtime.inbound()
    await runtime.service.run_once()

    class ProcessStopped(BaseException):
        pass

    def stop_sync(*args: Any, **kwargs: Any) -> None:
        raise ProcessStopped()

    async def stop_async(*args: Any, **kwargs: Any) -> bool:
        raise ProcessStopped()

    with monkeypatch.context() as patch:
        if boundary == "before_outbox":
            patch.setattr(WhatsAppLiveMessageProcessor, "enqueue_ai_reply", stop_sync)
        else:
            patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", stop_async)
        with pytest.raises(ProcessStopped):
            await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        rows = session.scalars(select(OutboundMessageAttemptModel)).all()
        assert len(rows) == 1 and rows[0].status == "sent"
        assert session.scalars(select(AIMemoryModel)).one().revision == 1
    assert len(provider.stages) == 4
