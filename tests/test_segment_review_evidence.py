"""Evidence projection carries references, never a decision to approve prose."""

import pytest
from app.application.generative_ai.response_validation import review_evidence
from app.domain.generative_ai.contracts import ProviderError

from tests.test_conversational_response import segment, synthetic_context
from tests.test_response_next_steps import draft_with


def test_selected_claim_evidence_is_exact_and_does_not_add_authority() -> None:
    context = synthetic_context()
    claim = context.authorized_claims[0]
    draft = draft_with([segment(claim_refs=[claim.id], need_refs=["need_age"])])
    projected = review_evidence(context, draft)
    selected = projected[0]["commercial_evidence"]
    assert isinstance(selected, list)
    assert selected[0]["claim"] == claim.model_dump()
    expected = {f.id: f.model_dump() for f in context.business_facts}
    assert selected[0]["facts"] == [expected[ref] for ref in claim.fact_refs]
    assert "approved" not in projected[0]
    assert projected[0]["customer_context"] == [context.customer_needs[0].model_dump()]


@pytest.mark.parametrize("field", ["claim_refs", "need_refs"])
def test_unknown_refs_do_not_gain_an_evidence_projection(field: str) -> None:
    with pytest.raises(ProviderError, match="INVALID_REFERENCE"):
        review_evidence(
            synthetic_context(), draft_with([segment(**{field: ["invented"]})])
        )


def test_claim_without_its_fact_cannot_be_projected() -> None:
    context = synthetic_context()
    claim = context.authorized_claims[0]
    context = context.model_copy(update={"business_facts": []})
    with pytest.raises(ProviderError, match="INVALID_REFERENCE"):
        review_evidence(context, draft_with([segment(claim_refs=[claim.id])]))
