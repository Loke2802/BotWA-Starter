"""Offline fidelity regression: two descriptions do not grant comparative authority."""

import pytest
from app.application.generative_ai.response_context import build_context
from app.application.generative_ai.response_validation import (
    digest,
    validate_draft,
    validate_review,
)
from app.domain.generative_ai.contracts import AdviserResult, AIConfig, ProviderError
from app.domain.generative_ai.response_contracts import (
    ConversationalDraft,
    CustomerTurn,
    SemanticReview,
    ValidatedResponseContext,
)

from tests.test_conversational_response import segment
from tests.test_knowledge_paraphrase import policy


def descriptions() -> ValidatedResponseContext:
    texts = {
        "corporate": "Una web corporativa comunica la identidad del negocio.",
        "catalog": "Un catálogo web presenta productos o servicios de forma ordenada.",
    }
    result = AdviserResult.model_validate(
        {
            "tone": "understood",
            "question_key": None,
            "handoff_requested": False,
            "recommendations": [],
            "knowledge": [
                {"source_ref": ref, "quote": text} for ref, text in texts.items()
            ],
        }
    )
    return build_context(
        "descriptions",
        result,
        AIConfig(),
        {},
        {
            ref: {"content": text, "version": "v1", "response_expression": policy(text)}
            for ref, text in texts.items()
        },
        customer_turn=CustomerTurn(
            message_ref="incoming", text="¿Qué diferencia hay entre ambas opciones?"
        ),
    )


def proposal(
    context: ValidatedResponseContext, kind: str, text: str
) -> ConversationalDraft:
    return ConversationalDraft.model_validate(
        {
            "schema_version": "1",
            "context_id": context.context_id,
            "segments": [
                segment(
                    id="explanation",
                    kind=kind,
                    text=text,
                    claim_refs=[c.id for c in context.authorized_claims],
                )
            ],
        }
    )


def test_two_descriptions_do_not_require_or_grant_comparative_authority() -> None:
    context = descriptions()
    assert context.authorized_comparisons == []
    assert all(c.expression_policy == "paraphrase" for c in context.authorized_claims)
    draft = proposal(
        context,
        "recommendation",
        "La web corporativa presenta la identidad de tu negocio. "
        "El catálogo web organiza la presentación de productos o servicios.",
    )
    assert validate_draft(context, draft, 3500) == draft.segments[0].text
    assert context.authorized_comparisons == []


def test_customer_comparison_request_does_not_authorize_comparison() -> None:
    context = descriptions()
    draft = proposal(
        context, "comparison", "La web corporativa es mejor que el catálogo."
    )
    with pytest.raises(ProviderError, match="UNSUPPORTED_COMPARISON"):
        validate_draft(context, draft, 3500)


def test_changing_segment_label_cannot_bypass_semantic_review() -> None:
    context = descriptions()
    draft = proposal(
        context, "recommendation", "La web corporativa es mejor que el catálogo."
    )
    text = validate_draft(context, draft, 3500)
    review = SemanticReview.model_validate(
        {
            "schema_version": "1",
            "context_id": context.context_id,
            "draft_digest": digest(text),
            "approved": False,
            "segments": [
                {
                    "segment_id": "explanation",
                    "approved": False,
                    "reason_code": "UNSUPPORTED_COMPARISON",
                    "unsupported_claim_refs": [context.authorized_claims[0].id],
                }
            ],
        }
    )
    with pytest.raises(ProviderError, match="REVIEW_UNSUPPORTED_COMPARISON"):
        validate_review(context, draft, text, review)
