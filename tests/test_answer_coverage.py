"""Offline two-description coverage; providers are authored fakes, never Luna."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.application.generative_ai import response_pipeline
from app.application.generative_ai.answer_coverage import (
    complete_descriptions,
    requested_descriptions,
    retrieval_words,
)
from app.application.generative_ai.response_context import build_context
from app.application.generative_ai.response_continuation import safe_continuation
from app.application.generative_ai.response_validation import validate_draft
from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    Generation,
    ProviderError,
    Usage,
)
from app.domain.generative_ai.response_contracts import (
    ConversationalDraft,
    CustomerTurn,
)
from app.infrastructure.models.ai_generation import (
    AIAttemptModel,
    AIJobModel,
    AIResponseCheckpointModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.operations.ai_consumer import dispatch_one
from pydantic import BaseModel
from sqlalchemy import select

from tests.test_conversational_response import segment
from tests.test_generative_ai import Runtime, runtime
from tests.test_knowledge_paraphrase import ParaphraseProvider, policy, prepare
from tests.test_whatsapp_live_processor_repository import cipher

__all__ = ["runtime"]
KIT = "El kit educativo permite explorar historias mediante el juego."
BOOK = "El libro ilustrado presenta relatos con dibujos para facilitar su consulta."
QUESTION = "¿Qué me aporta un kit educativo y qué me aporta un libro ilustrado?"
EXPLORE = "¿Cuál de estas opciones te gustaría explorar?"


@pytest.mark.parametrize(
    "utterance",
    [
        "Qué me aporta un kit educativo y qué me aporta un libro ilustrado",
        "Como me ayudaria un kit educativo y como me ayudaria un libro ilustrado",
        "Explícame el kit educativo y el libro ilustrado para mi caso",
        "Quiero entender el kit educativo y el libro ilustrado",
        "Explain kit educativo and libro ilustrado",
    ],
)
def test_explicit_explanation_without_question_mark_covers_both_sources(
    utterance: str,
) -> None:
    result, sources = evidence()
    refs = requested_descriptions(utterance, sources)
    assert refs == ["kit", "book"]
    context = build_context(
        "unpunctuated",
        complete_descriptions(result, refs, sources),
        AIConfig(),
        {},
        sources,
        customer_turn=CustomerTurn(message_ref="inbound", text=utterance),
    )
    assert len(context.required_claim_refs) == 2
    assert "explore_options" in context.allowed_next_steps
    assert "clarify_request" not in context.allowed_next_steps
    assert context.authorized_comparisons == []


@pytest.mark.parametrize(
    "utterance",
    [
        "No me expliques el kit educativo y el libro ilustrado",
        "Ya conozco el kit educativo y el libro ilustrado",
        "Don't explain kit educativo and libro ilustrado",
    ],
)
def test_unpunctuated_negation_and_statements_do_not_expand_coverage(
    utterance: str,
) -> None:
    _, sources = evidence()
    assert requested_descriptions(utterance, sources) == []


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué me aporta un kit educativo?",
        "No quiero kit educativo; ¿tienes libro ilustrado?",
        "¿Qué me aporta un equipo distinto y qué hace otro producto?",
        "El kit educativo y el libro ilustrado son opciones.",
    ],
)
def test_coverage_ignores_implicit_subjects_negation_or_statements(
    question: str,
) -> None:
    _, sources = evidence()
    assert requested_descriptions(question, sources) == []


@pytest.mark.parametrize(
    "change", ["duplicate", "unclassified", "stale", "protected", "catalog"]
)
def test_coverage_requires_two_unambiguous_opted_in_descriptions(change: str) -> None:
    result, sources = evidence()
    if change == "duplicate":
        sources["duplicate"] = dict(sources["book"])
    elif change == "unclassified":
        sources["book"].pop("response_expression")
    elif change == "stale":
        sources["book"]["response_expression"]["content_sha256"] = "0" * 64
    elif change == "catalog":
        sources["book"]["catalog"] = {"name": "Libro", "attributes": []}
    else:
        sources["book"]["content"] = "Incluye entrega y cuesta cien soles."
        sources["book"]["response_expression"] = policy(sources["book"]["content"])
    refs = requested_descriptions(QUESTION, sources)
    assert refs == []
    assert complete_descriptions(result, refs, sources) == result


def test_explicit_labels_are_accent_insensitive_ordered_and_not_comparative() -> None:
    result, sources = evidence()
    question = "¿LIBRO ILUSTRADO y kit educativo: qué hace cada uno?"
    assert requested_descriptions(question, sources) == ["book", "kit"]
    result = complete_descriptions(result, ["book", "kit"], sources)
    context = build_context(
        "ctx",
        result,
        AIConfig(),
        {},
        sources,
        customer_turn=CustomerTurn(message_ref="turn", text=question),
    )
    assert len(context.required_claim_refs) == 2
    assert context.authorized_comparisons == []
    assert context.business_facts[0].authorized_text == BOOK
    assert not context.products
    handoff = result.model_copy(update={"handoff_requested": True})
    assert complete_descriptions(handoff, ["kit", "book"], sources) == handoff
    old = context.model_dump(exclude={"required_claim_refs"})
    assert type(context).model_validate(old).required_claim_refs == []


def test_retrieval_input_is_bounded_and_current_turn_precedes_model_terms() -> None:
    terms = retrieval_words(["unrelated " * 100], QUESTION * 100)
    assert terms[:4] == ["kit", "educativo", "libro", "ilustrado"]
    assert len(terms) <= 24 and len(terms) == len(set(terms))
    assert all(len(t) <= 50 for t in terms)


def test_rejected_comparison_keeps_facts_without_repeated_offer() -> None:
    result, sources = evidence()
    text = safe_continuation(result, AIConfig(), {}, sources, [EXPLORE], QUESTION)
    assert KIT in text and BOOK in text and "?" not in text
    assert "asesor" not in text and "detalle necesitas" not in text


def evidence() -> tuple[AdviserResult, dict[str, dict[str, Any]]]:
    sources = {
        ref: {
            "version": "v1",
            "title": title,
            "content": content,
            "response_expression": policy(content),
        }
        for ref, title, content in [
            ("kit", "Kit educativo: descripción general", KIT),
            ("book", "Libro ilustrado: descripción general", BOOK),
        ]
    }
    result = AdviserResult.model_validate(
        {
            "tone": "unknown",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [],
            "knowledge": [
                {"source_ref": ref, "quote": row["content"]}
                for ref, row in sources.items()
            ],
        }
    )
    return result, sources


def test_clear_two_option_question_does_not_ask_customer_to_clarify_it_again() -> None:
    result, sources = evidence()
    text = safe_continuation(result, AIConfig(), {}, sources, [], QUESTION)
    assert text == "\n\n".join([KIT, BOOK, EXPLORE])


def test_draft_must_explain_each_required_description_before_followup() -> None:
    result, sources = evidence()
    context = build_context(
        "ctx",
        result,
        AIConfig(),
        {},
        sources,
        customer_turn=CustomerTurn(message_ref="current", text=QUESTION),
    )
    draft = ConversationalDraft.model_validate(
        {
            "schema_version": "1",
            "context_id": "ctx",
            "segments": [
                segment(
                    kind="recommendation",
                    text="El kit permite explorar historias jugando.",
                    claim_refs=["claim_knowledge_0"],
                )
            ],
        }
    )
    with pytest.raises(ProviderError, match="INCOMPLETE_EXPLANATION"):
        validate_draft(context, draft, 3500)
    assert "clarify_request" not in context.allowed_next_steps


class PartialProvider(ParaphraseProvider):
    def __init__(self, draft_both: bool) -> None:
        super().__init__()
        self.draft_both = draft_both
        self.reject = True

    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        data = json.loads(context)
        if stage not in {"adviser", "conversational_render"}:
            return await super().generate(stage=stage, context=context, schema=schema)
        self.stages.append(stage)
        self.calls.append(data)
        if stage == "adviser":
            # Discovery only searched "dinosaurio". Adviser intentionally omits
            # the second requested description, even if retrieval supplies it.
            ref = next(
                k
                for k, v in data["sources"].items()
                if v["title"].startswith("Kit educativo:")
            )
            response = {
                "tone": "unknown",
                "question_key": None,
                "handoff_requested": False,
                "recommendations": [],
                "knowledge": [
                    {"source_ref": ref, "quote": data["sources"][ref]["content"]}
                ],
            }
        else:
            claims = (
                data["authorized_claims"]
                if self.draft_both
                else data["authorized_claims"][:1]
            )
            response = {
                "schema_version": "1",
                "context_id": data["context_id"],
                "segments": [
                    segment(
                        id=f"fact_{i}",
                        kind="recommendation",
                        text="Descripción propuesta.",
                        claim_refs=[claim["id"]],
                    )
                    for i, claim in enumerate(claims)
                ],
            }
        return Generation(
            data=json.dumps(response),
            usage=Usage(input_tokens=10, output_tokens=10, model="gpt-6-luna"),
        )


async def seed_question(
    runtime: Runtime, draft_both: bool, crowded: bool = False
) -> PartialProvider:
    prepare(runtime)
    with runtime.sessions() as session:
        kit = session.get(KnowledgeEntryModel, runtime.item_id)
        assert kit
        kit.title = "Kit educativo: descripción general"
        kit.content = KIT + " Dinosaurio de historias."
        kit.metadata_data = {"response_expression": policy(kit.content)}
        session.add(
            KnowledgeEntryModel(
                id=UUID(int=2**128 - 1),
                organization_id=kit.organization_id,
                bot_id=kit.bot_id,
                title="Libro ilustrado: descripción general",
                content=BOOK,
                status="published",
                created_by_user_id=kit.created_by_user_id,
                metadata_data={"response_expression": policy(BOOK)},
            )
        )
        if crowded:
            for i in range(1, 14):
                session.add(
                    KnowledgeEntryModel(
                        id=UUID(int=i),
                        organization_id=kit.organization_id,
                        bot_id=kit.bot_id,
                        title="Dato general",
                        content="Dinosaurio para otra consulta.",
                        status="published",
                        created_by_user_id=kit.created_by_user_id,
                        metadata_data={},
                    )
                )
        session.commit()
    provider = PartialProvider(draft_both)
    runtime.service.provider = provider
    await runtime.inbound()
    with runtime.sessions() as session:
        message = session.scalars(
            select(MessageModel).where(MessageModel.direction == "inbound")
        ).one()
        message.text_ciphertext = cipher().encrypt(
            "Mi sobrino tiene 5 años y quiere un dinosaurio. " + QUESTION
        )
        session.commit()
    return provider


@pytest.mark.parametrize("draft_both", [False, True])
async def test_omitted_description_recovered_without_extra_provider_calls(
    runtime: Runtime, draft_both: bool
) -> None:
    provider = await seed_question(runtime, draft_both, crowded=True)
    assert await runtime.service.run_once()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready", job.error_code
        assert len(job.sources) == 2
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == "fallback"
        assert cp.reason_code == (
            "REVIEW_UNSUPPORTED_CLAIM" if draft_both else "INCOMPLETE_EXPLANATION"
        )
        out = session.scalars(select(OutboundMessageAttemptModel)).one()
        reply = cipher().decrypt(out.message_ciphertext)
        assert BOOK in reply and KIT in reply and reply.endswith(EXPLORE)
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    await dispatch_one(runtime.service)
    await dispatch_one(runtime.service)
    assert runtime.service.claim() is None  # Canonical worker terminal cleanup.
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "sent"
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.ciphertext is None  # Text still cleans up at terminal state.
        attempts = list(session.scalars(select(AIAttemptModel)))
        adviser = next(a for a in attempts if a.stage == "adviser")
        diag = adviser.parameters["source_coverage"]
        assert isinstance(diag, dict)
        assert diag["retrieved_count"] <= 12
        assert len(diag["proposed_refs"]) == 1 and len(diag["validated_refs"]) == 2
        assert len(diag["requested_refs"]) == 2
        assert KIT not in json.dumps(diag) and QUESTION not in json.dumps(diag)
        if draft_both:
            review = next(a for a in attempts if a.stage == "semantic_review")
            summary = review.parameters["review_summary"]
            assert isinstance(summary, dict)
            assert summary["rejected_codes"] == {"UNSUPPORTED_CLAIM": 2}
        assert not any(a.result == "reserved" for a in attempts)
        assert len(list(session.scalars(select(OutboundMessageAttemptModel)))) == 1
    assert provider.stages == (
        ["discovery", "adviser", "conversational_render", "semantic_review"]
        if draft_both
        else ["discovery", "adviser", "conversational_render"]
    )


async def test_added_description_is_fenced_before_dispatch(
    runtime: Runtime,
) -> None:
    await seed_question(runtime, draft_both=False)
    await runtime.service.run_once()
    with runtime.sessions() as session:
        book = session.get(KnowledgeEntryModel, UUID(int=2**128 - 1))
        assert book
        book.status = "archived"
        session.commit()
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert not list(session.scalars(select(OutboundMessageAttemptModel)))


async def test_disabled_conversational_lane_keeps_original_source_path(
    runtime: Runtime,
) -> None:
    provider = await seed_question(runtime, draft_both=True)
    with runtime.sessions() as session:
        bot = session.get(BotModel, runtime.channel.bot_id)
        assert bot
        config = AIConfig.model_validate(bot.settings["generative_ai"]).model_dump()
        config["conversational_response"] = {"enabled": False}
        bot.settings = {"generative_ai": config}
        session.commit()
    await runtime.service.run_once()
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready" and len(job.sources) == 1
        assert str(UUID(int=2**128 - 1)) not in job.sources
        assert all(
            "source_coverage" not in a.parameters
            for a in session.scalars(select(AIAttemptModel))
        )
    assert provider.stages == ["discovery", "adviser"]


async def test_ranked_retrieval_remains_scoped_before_limit(runtime: Runtime) -> None:
    await seed_question(runtime, draft_both=False, crowded=True)
    with runtime.sessions() as session:
        for cross_tenant in [False, True]:
            org = (
                OrganizationModel(id=uuid4(), name="Other", slug=str(uuid4()))
                if cross_tenant
                else None
            )
            if org:
                session.add(org)
                session.flush()
            other = BotModel(
                id=uuid4(),
                organization_id=org.id if org else runtime.channel.organization_id,
                name="Other",
                slug=str(uuid4()),
                settings={},
            )
            session.add(other)
            session.flush()
            session.add(
                KnowledgeEntryModel(
                    organization_id=other.organization_id,
                    bot_id=other.id,
                    title="Kit educativo: descripción general",
                    content="PRIVATE FOREIGN FACT",
                    status="published",
                    created_by_user_id=runtime.channel.created_by_user_id,
                    metadata_data={
                        "response_expression": policy("PRIVATE FOREIGN FACT")
                    },
                )
            )
        session.commit()
    claim = runtime.service.claim()
    assert claim
    sources = runtime.service.retrieve(*claim, ["dinosaurio"], QUESTION)
    assert len(sources) == 12
    assert str(runtime.item_id) in sources and str(UUID(int=2**128 - 1)) in sources
    assert "PRIVATE" not in json.dumps(sources)


async def test_coverage_restart_reuses_calls_and_metadata(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = await seed_question(runtime, draft_both=True)
    original = response_pipeline.save

    class ProcessStopped(BaseException):
        pass

    def stop(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        if args[-1] == "semantic_review_done":
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
    with runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready" and len(job.sources) == 2
        adviser = session.scalars(
            select(AIAttemptModel).where(AIAttemptModel.stage == "adviser")
        ).one()
        diag = adviser.parameters["source_coverage"]
        assert isinstance(diag, dict) and len(diag["validated_refs"]) == 2
    assert provider.stages == [
        "discovery",
        "adviser",
        "conversational_render",
        "semantic_review",
    ]
