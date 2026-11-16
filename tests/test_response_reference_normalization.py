"""Representation-only repairs must never supply missing permission."""

from typing import Any

import pytest
from app.application.generative_ai.response_validation import (
    normalize_conversation_references,
    validate_draft,
)
from app.domain.generative_ai.contracts import ProviderError
from app.domain.generative_ai.response_contracts import AllowedQuestion

from tests.test_conversational_response import segment, synthetic_context
from tests.test_response_next_steps import draft_with, unknown


def test_misplaced_known_next_step_keeps_text_and_authority() -> None:
    context = synthetic_context()
    context = context.model_copy(
        update={
            "allowed_next_steps": {
                **context.allowed_next_steps,
                "explore_options": (
                    "Preguntar que opcion desea explorar; no ejecutar acciones."
                ),
            }
        }
    )
    original = draft_with(
        [
            segment(
                id="choice",
                kind="question",
                text="¿Cuál de las opciones te gustaría explorar?",
                question_ref="explore_options",
                need_refs=["need_age"],
            )
        ]
    )
    with pytest.raises(ProviderError, match="REPEATED_OR_UNKNOWN_QUESTION"):
        validate_draft(context, original, 3500)
    corrected = normalize_conversation_references(context, original)
    assert corrected.segments[0].kind == "next_step"
    assert corrected.segments[0].question_ref is None
    assert corrected.segments[0].next_step_ref == "explore_options"
    assert corrected.segments[0].text == original.segments[0].text
    assert corrected.segments[0].need_refs == original.segments[0].need_refs
    assert corrected.segments[0].claim_refs == []
    assert original.segments[0].question_ref == "explore_options"
    assert validate_draft(context, corrected, 3500) == original.segments[0].text
    assert normalize_conversation_references(context, corrected) is corrected


@pytest.mark.parametrize(
    "overrides",
    [
        {"question_ref": "invented"},
        {"next_step_ref": "human_offer"},
        {"uncertainty_ref": "insufficient_information"},
        {"claim_refs": ["invented"]},
        {"kind": "acknowledgement"},
    ],
)
def test_normalization_does_not_rescue_unknown_or_conflicting_refs(
    overrides: dict[str, Any],
) -> None:
    context = synthetic_context()
    original = draft_with(
        [
            segment(
                kind="question",
                question_ref="human_offer",
                text="¿Revisamos tu duda?",
            )
            | overrides
        ]
    )
    assert normalize_conversation_references(context, original) is original
    with pytest.raises(ProviderError):
        validate_draft(context, original, 3500)


def test_ambiguous_permission_and_wrong_context_are_not_reinterpreted() -> None:
    context = synthetic_context()
    draft = draft_with(
        [
            segment(
                kind="question",
                question_ref="human_offer",
                text="¿Revisamos tu duda?",
            )
        ]
    )
    ambiguous = context.model_copy(
        update={
            "allowed_questions": [
                AllowedQuestion(
                    id="human_offer", need_key="age", purpose="Pregunta configurada"
                ),
            ]
        }
    )
    assert normalize_conversation_references(ambiguous, draft) is draft
    wrong = context.model_copy(update={"context_id": "wrong"})
    assert normalize_conversation_references(wrong, draft) is draft
    with pytest.raises(ProviderError, match="CONTEXT_MISMATCH"):
        validate_draft(wrong, draft, 3500)


def test_normalized_step_still_cannot_precede_the_answer() -> None:
    context = synthetic_context()
    draft = draft_with(
        [
            segment(
                kind="question",
                question_ref="human_offer",
                text="¿Revisamos tu duda?",
            ),
            unknown(),
        ]
    )
    with pytest.raises(ProviderError, match="PREMATURE_NEXT_STEP"):
        validate_draft(context, normalize_conversation_references(context, draft), 3500)
