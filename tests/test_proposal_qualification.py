"""Offline policy/transport contracts; not live model-quality acceptance."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from app.application.generative_ai.response_context import build_context
from app.application.generative_ai.response_continuation import safe_continuation
from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    Generation,
    NeedDefinition,
)
from app.infrastructure.models.ai_generation import (
    AIJobModel,
    AIResponseCheckpointModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.operations.ai_consumer import dispatch_one
from pydantic import BaseModel
from sqlalchemy import select

from tests.test_generative_ai import FakeProvider, Runtime, runtime

__all__ = ["runtime"]


class TransferSelectingProvider(FakeProvider):
    def __init__(self, discovery_handoff: bool) -> None:
        super().__init__()
        self.discovery_handoff = discovery_handoff

    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        generation = await super().generate(stage=stage, context=context, schema=schema)
        data = json.loads(generation.data)
        data["handoff_requested"] = (
            self.discovery_handoff if stage == "discovery" else True
        )
        return generation.model_copy(update={"data": json.dumps(data)})


@pytest.mark.parametrize(
    ("qualification", "customer_handoff", "expected"),
    [(True, False, "sent"), (True, True, "handoff"), (False, False, "handoff")],
)
async def test_fact_selector_cannot_add_transfer_in_qualification_mode(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    qualification: bool,
    customer_handoff: bool,
    expected: str,
) -> None:
    from tests.plan_support import allow_all_plan_enforcement

    monkeypatch.setattr(
        "app.operations.ai_consumer.PlanEnforcementService",
        lambda repository: allow_all_plan_enforcement(),
    )
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot is not None
        config = AIConfig.model_validate(bot.settings["generative_ai"])
        bot.settings = {
            "generative_ai": config.model_copy(
                update={"qualify_for_proposal": qualification}
            ).model_dump()
        }
        session.add(
            BusinessConfigurationModel(
                bot_id=bot.id,
                business_name="Fictional business",
                description="Test",
                service_instructions="Use published knowledge",
                handoff_enabled=True,
            )
        )
        session.commit()
    runtime.service.provider = TransferSelectingProvider(customer_handoff)
    await runtime.inbound()
    await runtime.service.run_once()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        row = session.scalars(select(AIJobModel)).one()
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == expected
        attempts = list(session.scalars(select(OutboundMessageAttemptModel)))
        handoffs = list(session.scalars(select(HandoffSessionModel)))
        if expected == "sent":
            assert len(attempts) == 1 and attempts[0].attempt_count == 1
            assert not handoffs
        else:
            assert not attempts
            assert len(handoffs) == 1 and handoffs[0].status == "waiting_human"


def test_qualification_uses_remaining_question_without_restarting() -> None:
    config = AIConfig(
        qualify_for_proposal=True,
        needs=[
            NeedDefinition(
                key="business",
                attribute="business",
                question="¿A qué se dedica tu negocio?",
            ),
            NeedDefinition(
                key="functions",
                attribute="functions",
                question="¿Qué necesitas que puedan hacer los visitantes?",
            ),
        ],
    )
    result = AdviserResult(
        tone="unknown",
        question_key=None,
        handoff_requested=False,
        recommendations=[],
        knowledge=[],
    )
    memory = {"business": {"value": "taller", "message_ref": "first"}}
    context = build_context("qualification", result, config, memory, {})
    assert context.qualify_for_proposal
    assert "human_offer" not in context.allowed_next_steps
    assert [q.need_key for q in context.allowed_questions] == ["functions"]
    reply = safe_continuation(
        result, config, memory, {}, [], "¿Cuál es el precio exacto?"
    )
    assert "precio exacto" in reply
    assert "¿Qué necesitas que puedan hacer los visitantes?" in reply
    assert "asesor" not in reply
    assert "dedica" not in reply
    assert "250" not in reply and "450" not in reply


def test_qualification_preserves_complete_published_price_scope() -> None:
    # Fictional source: prices are tenant data, never embedded in engine logic.
    clause = "Landing básica: S/250. Precio final según alcance en la propuesta PDF."
    result = AdviserResult(
        tone="unknown",
        question_key=None,
        handoff_requested=False,
        recommendations=[],
        knowledge=[{"source_ref": "ref", "quote": clause}],
    )
    sources = {"ref": {"version": "v1", "content": clause}}
    config = AIConfig(qualify_for_proposal=True)
    context = build_context("price-scope", result, config, {}, sources)
    assert context.canonical_clauses == {"knowledge_0": clause}
    assert context.authorized_claims[0].expression_policy == "canonical_clause"
    assert "human_offer" not in context.allowed_next_steps
    assert not AIConfig().qualify_for_proposal


async def test_selector_transfer_still_runs_render_and_review(runtime: Runtime) -> None:
    from tests.test_knowledge_paraphrase import ParaphraseProvider, prepare

    class Provider(ParaphraseProvider):
        async def generate(
            self, *, stage: str, context: str, schema: type[BaseModel]
        ) -> Generation:
            generation = await super().generate(
                stage=stage, context=context, schema=schema
            )
            if stage == "adviser":
                data = json.loads(generation.data)
                data["handoff_requested"] = True
                return generation.model_copy(update={"data": json.dumps(data)})
            return generation

    prepare(runtime)
    provider = Provider()
    runtime.service.provider = provider
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        config = AIConfig.model_validate(bot.settings["generative_ai"])
        bot.settings = {
            "generative_ai": config.model_copy(
                update={"qualify_for_proposal": True}
            ).model_dump()
        }
        session.commit()
    await runtime.inbound()
    await runtime.service.run_once()
    assert provider.stages == [
        "discovery",
        "adviser",
        "conversational_render",
        "semantic_review",
    ]
    context = next(c for c in provider.calls if "allowed_next_steps" in c)
    assert context["qualify_for_proposal"] is True
    assert "human_offer" not in context["allowed_next_steps"]
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        cp = session.get(AIResponseCheckpointModel, job.id)
        assert cp and cp.outcome == "approved"
        out = session.scalars(select(OutboundMessageAttemptModel)).one()
        assert out.status == "sent" and out.attempt_count == 1
        assert not session.scalars(select(HandoffSessionModel)).all()
