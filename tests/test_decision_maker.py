from uuid import uuid4

from app.core.business.decision_maker import DecisionMaker
from app.domain.business.contracts import (
    BusinessConstraint,
    BusinessConstraints,
    BusinessContext,
    BusinessIntent,
    BusinessOptions,
    BusinessRequest,
)


def _context(content: str = "Hola") -> BusinessContext:
    request = BusinessRequest(
        content=content,
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    return BusinessContext(request=request, intent="")


def test_decide_returns_business_options() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=True)
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert isinstance(result, BusinessOptions)


def test_decide_creates_respond_option_for_greeting() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=True)
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert len(result.options) == 1
    assert result.options[0].action == "respond"
    assert result.options[0].score == 0.90


def test_decide_creates_respond_and_query_for_price_inquiry() -> None:
    context = _context()
    intent = BusinessIntent(name="price_inquiry")
    constraints = BusinessConstraints(
        is_feasible=True,
        constraints=[
            BusinessConstraint(
                rule_id="BR-KNOWLEDGE-REQUIRED",
                description="test",
                applies=True,
            ),
        ],
    )
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert len(result.options) == 2
    assert result.options[0].action == "respond"
    assert result.options[1].action == "query_knowledge"


def test_decide_respond_selected_for_high_score() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=True)
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert result.selected_index == 0


def test_decide_respond_selected_even_with_knowledge() -> None:
    context = _context()
    intent = BusinessIntent(name="price_inquiry")
    constraints = BusinessConstraints(
        is_feasible=True,
        constraints=[
            BusinessConstraint(
                rule_id="BR-KNOWLEDGE-REQUIRED",
                description="test",
                applies=True,
            ),
        ],
    )
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert result.selected_index == 0
    assert result.options[0].score == 0.90
    assert result.options[1].score == 0.85


def test_decide_unknown_score() -> None:
    context = _context()
    intent = BusinessIntent(name="unknown")
    constraints = BusinessConstraints(is_feasible=True)
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert result.options[0].score == 0.50


def test_decide_not_feasible_score() -> None:
    context = _context()
    intent = BusinessIntent(name="unknown")
    constraints = BusinessConstraints(is_feasible=False)
    maker = DecisionMaker()

    result = maker.decide(context, intent, constraints)

    assert result.options[0].score == 0.30
