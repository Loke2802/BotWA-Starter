"""Authored contract tests; these do not measure live model quality."""

import json
from typing import Any

import pytest
from app.application.generative_ai.response_validation import (
    review_permissions,
    validate_draft,
)
from app.domain.generative_ai.contracts import Generation, ProviderError, Usage
from app.domain.generative_ai.response_contracts import ConversationalDraft
from app.infrastructure.models.ai_generation import AIResponseCheckpointModel
from pydantic import BaseModel
from sqlalchemy import select

from tests.test_conversational_response import segment, synthetic_context
from tests.test_customer_context_response import CustomerContextProvider
from tests.test_generative_ai import Runtime, runtime
from tests.test_knowledge_paraphrase import prepare

__all__ = ["runtime"]


def human_offer() -> dict[str, Any]:
    return segment(
        id="offer",
        kind="next_step",
        text="¿Prefieres revisar esa duda con un asesor?",
        next_step_ref="human_offer",
    )


def unknown() -> dict[str, Any]:
    return segment(
        id="unknown",
        kind="uncertainty",
        text="No tengo confirmado ese detalle.",
        uncertainty_ref="insufficient_information",
    )


def draft_with(segments: list[dict[str, Any]]) -> ConversationalDraft:
    return ConversationalDraft.model_validate(
        {"schema_version": "1", "context_id": "ctx", "segments": segments}
    )


def test_offer_uses_its_own_permission_without_inventing_a_commercial_claim() -> None:
    context = synthetic_context()
    draft = draft_with([unknown(), human_offer()])
    assert "asesor" in validate_draft(context, draft, 3500)
    permissions = review_permissions(context, draft)
    assert permissions[-1] == {
        "segment_id": "offer",
        "kind": "next_step",
        "ref": "human_offer",
        "scope": context.allowed_next_steps["human_offer"],
    }
    assert draft.segments[-1].claim_refs == []
    assert permissions[0]["scope"] == context.uncertainties["insufficient_information"]


def test_permission_cannot_be_forged_by_the_draft() -> None:
    context = synthetic_context()
    step = human_offer()
    step["next_step_ref"] = "promise_booking"
    draft = draft_with([step])
    with pytest.raises(ProviderError, match="UNKNOWN_NEXT_STEP"):
        validate_draft(context, draft, 3500)
    with pytest.raises(ProviderError, match="INVALID_REFERENCE"):
        review_permissions(context, draft)


@pytest.mark.parametrize("kind", ["next_step", "question"])
def test_question_cannot_precede_the_available_answer(kind: str) -> None:
    context = synthetic_context()
    offer = human_offer()
    offer["kind"] = kind
    with pytest.raises(ProviderError, match="PREMATURE_NEXT_STEP"):
        validate_draft(context, draft_with([offer, unknown()]), 3500)


def test_supported_explanation_precedes_the_offer() -> None:
    context = synthetic_context()
    claim = context.authorized_claims[0]
    explanation = segment(
        id="explain",
        kind="recommendation",
        text="{{clause:" + claim.required_clause_refs[0] + "}}",
        claim_refs=[claim.id],
    )
    draft = draft_with([explanation, unknown(), human_offer()])
    text = validate_draft(context, draft, 3500)
    assert text.index("confirmado") < text.index("asesor")
    with pytest.raises(ProviderError, match="PREMATURE_NEXT_STEP"):
        validate_draft(context, draft_with([human_offer(), explanation]), 3500)


class NextStepProvider(CustomerContextProvider):
    """Authored reviewer verdicts verify plumbing, never semantic correctness."""

    def __init__(self, reject_offer: bool, misplaced_offer: bool = False) -> None:
        super().__init__()
        self.reject_offer = reject_offer
        self.misplaced_offer = misplaced_offer
        self.permissions_seen = False

    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        if stage not in {"conversational_render", "semantic_review"}:
            return await super().generate(stage=stage, context=context, schema=schema)
        data = json.loads(context)
        self.stages.append(stage)
        self.calls.append(data)
        if stage == "conversational_render":
            response = {
                "schema_version": "1",
                "context_id": data["context_id"],
                "segments": [
                    segment(
                        id="explain",
                        kind="recommendation",
                        text="Este recurso permite explorar historias jugando.",
                        claim_refs=[data["authorized_claims"][0]["id"]],
                    ),
                    unknown(),
                    human_offer(),
                ],
            }
            if self.reject_offer:
                response["segments"][-1][
                    "text"
                ] = "El asesor activara las reservas de tu proyecto."
            if self.misplaced_offer:
                response["segments"][-1].update(
                    kind="question", question_ref="human_offer", next_step_ref=None
                )
        else:
            permissions = data["conversation_permissions"]
            assert permissions[-1]["segment_id"] == "offer"
            assert (
                permissions[-1]["scope"]
                == data["context"]["allowed_next_steps"]["human_offer"]
            )
            self.permissions_seen = True
            if self.misplaced_offer:
                target = data["draft"]["segments"][-1]
                assert target["kind"] == "next_step"
                assert target["question_ref"] is None
                assert target["next_step_ref"] == "human_offer"
            response = {
                "schema_version": "1",
                "context_id": data["context"]["context_id"],
                "draft_digest": data["draft_digest"],
                "approved": not self.reject_offer,
                "segments": [
                    {
                        "segment_id": s["id"],
                        "approved": not (self.reject_offer and s["id"] == "offer"),
                        "reason_code": (
                            "UNSUPPORTED_CLAIM"
                            if self.reject_offer and s["id"] == "offer"
                            else "OK"
                        ),
                        "unsupported_claim_refs": [],
                    }
                    for s in data["draft"]["segments"]
                ],
            }
        return Generation(
            data=json.dumps(response),
            usage=Usage(input_tokens=10, output_tokens=10, model="gpt-6-luna"),
        )


@pytest.mark.parametrize("reject_offer", [False, True])
@pytest.mark.parametrize("misplaced_offer", [False, True])
async def test_permissions_reach_review_without_overriding_rejection(
    runtime: Runtime, reject_offer: bool, misplaced_offer: bool
) -> None:
    prepare(runtime)
    provider = NextStepProvider(reject_offer, misplaced_offer)
    runtime.service.provider = provider
    await runtime.inbound()
    assert await runtime.service.run_once()
    assert provider.permissions_seen
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == ("fallback" if reject_offer else "approved")
        assert cp.reason_code == ("REVIEW_UNSUPPORTED_CLAIM" if reject_offer else None)
