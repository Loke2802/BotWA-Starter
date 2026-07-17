from uuid import uuid4

import pytest
from app.domain.business.contracts import (
    BusinessContext,
    BusinessDecision,
    BusinessRequest,
)
from pydantic import ValidationError


def test_business_request_requires_content() -> None:
    with pytest.raises(ValidationError):
        BusinessRequest(
            content="",
            customer_id="customer-1",
            company_id="company-1",
            conversation_id=uuid4(),
        )


def test_business_request_requires_customer_id() -> None:
    with pytest.raises(ValidationError):
        BusinessRequest(
            content="Hello",
            customer_id="",
            company_id="company-1",
            conversation_id=uuid4(),
        )


def test_business_request_requires_company_id() -> None:
    with pytest.raises(ValidationError):
        BusinessRequest(
            content="Hello",
            customer_id="customer-1",
            company_id="",
            conversation_id=uuid4(),
        )


def test_business_context_holds_request_and_intent() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )
    context = BusinessContext(request=request, intent="greeting")

    assert context.request == request
    assert context.intent == "greeting"


def test_business_decision_holds_status_intent_message_confidence() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="greeting",
        message="Hello!",
        confidence="high",
    )

    assert decision.status == "accepted"
    assert decision.intent == "greeting"
    assert decision.message == "Hello!"
    assert decision.confidence == "high"
    assert decision.needs_knowledge is False


def test_business_decision_can_set_needs_knowledge() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="question",
        message="Let me check",
        confidence="medium",
        needs_knowledge=True,
    )

    assert decision.needs_knowledge is True
