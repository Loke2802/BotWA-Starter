from uuid import uuid4

from app.core.business.confidence_evaluator import ConfidenceEvaluator
from app.domain.business.contracts import (
    BusinessConstraints,
    BusinessContext,
    BusinessIntent,
    BusinessOption,
    BusinessRequest,
)


def _context() -> BusinessContext:
    request = BusinessRequest(
        content="Hola",
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    return BusinessContext(request=request, intent="")


def test_evaluate_returns_high() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=True)
    option = BusinessOption(action="respond", score=0.90)
    evaluator = ConfidenceEvaluator()

    result = evaluator.evaluate(context, intent, constraints, option)

    assert result == "high"


def test_evaluate_returns_medium() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=True)
    option = BusinessOption(action="respond", score=0.50)
    evaluator = ConfidenceEvaluator()

    result = evaluator.evaluate(context, intent, constraints, option)

    assert result == "medium"


def test_evaluate_returns_low() -> None:
    context = _context()
    intent = BusinessIntent(name="unknown")
    constraints = BusinessConstraints(is_feasible=True)
    option = BusinessOption(action="respond", score=0.30)
    evaluator = ConfidenceEvaluator()

    result = evaluator.evaluate(context, intent, constraints, option)

    assert result == "low"


def test_evaluate_low_when_not_feasible() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=False)
    option = BusinessOption(action="respond", score=0.90)
    evaluator = ConfidenceEvaluator()

    result = evaluator.evaluate(context, intent, constraints, option)

    assert result == "low"


def test_evaluate_low_when_unknown() -> None:
    context = _context()
    intent = BusinessIntent(name="unknown")
    constraints = BusinessConstraints(is_feasible=True)
    option = BusinessOption(action="respond", score=0.90)
    evaluator = ConfidenceEvaluator()

    result = evaluator.evaluate(context, intent, constraints, option)

    assert result == "low"


def test_evaluate_low_when_no_option() -> None:
    context = _context()
    intent = BusinessIntent(name="greeting")
    constraints = BusinessConstraints(is_feasible=True)
    evaluator = ConfidenceEvaluator()

    result = evaluator.evaluate(context, intent, constraints, None)

    assert result == "low"
