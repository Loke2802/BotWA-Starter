from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.domain.business.contracts import (
    ActionStep,
    BusinessActionPlan,
    BusinessConstraint,
    BusinessConstraints,
    BusinessContext,
    BusinessDecision,
    BusinessEvent,
    BusinessIntent,
    BusinessOption,
    BusinessOptions,
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


def test_business_context_intent_defaults_to_empty() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )
    context = BusinessContext(request=request)

    assert context.intent == ""


def test_business_context_defaults_customer_profile() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )
    context = BusinessContext(request=request)

    assert context.customer_profile == {}


def test_business_context_defaults_channel_metadata() -> None:
    request = BusinessRequest(
        content="Hello",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )
    context = BusinessContext(request=request)

    assert context.channel_metadata == {}


def test_business_decision_holds_status_intent_confidence() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="greeting",
        confidence="high",
    )

    assert decision.status == "accepted"
    assert decision.intent == "greeting"
    assert decision.confidence == "high"
    assert decision.needs_knowledge is False
    assert decision.knowledge_content is None


def test_business_decision_can_set_knowledge_content() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="question",
        confidence="medium",
        needs_knowledge=True,
        knowledge_content="Some knowledge content",
    )

    assert decision.needs_knowledge is True
    assert decision.knowledge_content == "Some knowledge content"


def test_business_intent_holds_name_and_confidence() -> None:
    intent = BusinessIntent(name="price_inquiry", confidence="high")

    assert intent.name == "price_inquiry"
    assert intent.confidence == "high"


def test_business_intent_default_confidence() -> None:
    intent = BusinessIntent(name="question")

    assert intent.name == "question"
    assert intent.confidence == "medium"


def test_business_intent_is_frozen() -> None:
    intent = BusinessIntent(name="support", confidence="high")

    with pytest.raises(ValidationError):
        intent.name = "question"  # type: ignore[misc]


def test_business_constraint_holds_fields() -> None:
    constraint = BusinessConstraint(
        rule_id="BR-001",
        description="Cliente debe ser mayor de edad",
        applies=True,
        reason="Edad verificada",
    )

    assert constraint.rule_id == "BR-001"
    assert constraint.applies is True
    assert constraint.reason == "Edad verificada"


def test_business_constraints_default_is_feasible() -> None:
    constraints = BusinessConstraints()

    assert constraints.is_feasible is True
    assert constraints.constraints == []


def test_business_constraints_with_multiple_rules() -> None:
    c1 = BusinessConstraint(rule_id="BR-001", description="Rule 1", applies=True)
    c2 = BusinessConstraint(rule_id="BR-002", description="Rule 2", applies=False)
    constraints = BusinessConstraints(constraints=[c1, c2], is_feasible=False)

    assert len(constraints.constraints) == 2
    assert constraints.is_feasible is False


def test_business_option_holds_action_and_score() -> None:
    option = BusinessOption(action="respond", score=0.95, confidence="high")

    assert option.action == "respond"
    assert option.score == 0.95
    assert option.confidence == "high"


def test_business_options_selected_index_default_none() -> None:
    options = BusinessOptions()

    assert options.selected_index is None
    assert options.options == []


def test_business_options_with_multiple_options() -> None:
    o1 = BusinessOption(action="respond", score=0.9)
    o2 = BusinessOption(action="escalate", score=0.3)
    options = BusinessOptions(options=[o1, o2], selected_index=0)

    assert len(options.options) == 2
    assert options.selected_index == 0


def test_action_step_holds_action_and_order() -> None:
    step = ActionStep(action="respond", target="customer", order=1)

    assert step.action == "respond"
    assert step.target == "customer"
    assert step.order == 1


def test_business_action_plan_holds_steps() -> None:
    step1 = ActionStep(action="respond", order=1)
    step2 = ActionStep(action="escalate", order=2)
    plan = BusinessActionPlan(steps=[step1, step2])

    assert len(plan.steps) == 2
    assert plan.total_steps == 0


def test_business_event_holds_type_and_source() -> None:
    event = BusinessEvent(
        event_type="objetivo_identificado",
        source="business_brain",
        conversation_id=uuid4(),
    )

    assert event.event_type == "objetivo_identificado"
    assert event.source == "business_brain"
    assert isinstance(event.conversation_id, UUID)


def test_business_event_generates_timestamp() -> None:
    event = BusinessEvent(event_type="test", source="bb")

    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo is UTC
