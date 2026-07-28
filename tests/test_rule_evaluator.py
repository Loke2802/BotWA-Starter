from uuid import uuid4

from app.core.business.rule_evaluator import RuleEvaluator
from app.domain.business.contracts import (
    BusinessConstraints,
    BusinessContext,
    BusinessIntent,
    BusinessRequest,
)


def _context_with_profile(
    content: str = "Hola",
    profile: dict[str, object] | None = None,
) -> BusinessContext:
    request = BusinessRequest(
        content=content,
        customer_id="c1",
        company_id="co1",
        conversation_id=uuid4(),
    )
    return BusinessContext(
        request=request,
        intent="",
        customer_profile=profile or {},
    )


def test_evaluate_returns_business_constraints() -> None:
    context = _context_with_profile(profile={"customer_id": "c1"})
    intent = BusinessIntent(name="price_inquiry")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    assert isinstance(result, BusinessConstraints)


def test_evaluate_intent_known_passes() -> None:
    context = _context_with_profile(profile={"customer_id": "c1"})
    intent = BusinessIntent(name="price_inquiry")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    br = [c for c in result.constraints if c.rule_id == "BR-INTENT-KNOWN"][0]
    assert br.applies is True
    assert "price_inquiry" in br.reason


def test_evaluate_intent_unknown_fails() -> None:
    context = _context_with_profile(profile={"customer_id": "c1"})
    intent = BusinessIntent(name="unknown")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    br = [c for c in result.constraints if c.rule_id == "BR-INTENT-KNOWN"][0]
    assert br.applies is False


def test_evaluate_customer_active_passes() -> None:
    context = _context_with_profile(profile={"customer_id": "c1", "name": "Juan"})
    intent = BusinessIntent(name="greeting")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    br = [c for c in result.constraints if c.rule_id == "BR-CUSTOMER-ACTIVE"][0]
    assert br.applies is True


def test_evaluate_customer_active_fails() -> None:
    context = _context_with_profile(profile={})
    intent = BusinessIntent(name="greeting")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    br = [c for c in result.constraints if c.rule_id == "BR-CUSTOMER-ACTIVE"][0]
    assert br.applies is False


def test_evaluate_knowledge_required_for_price_inquiry() -> None:
    context = _context_with_profile(profile={"customer_id": "c1"})
    intent = BusinessIntent(name="price_inquiry")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    br = [c for c in result.constraints if c.rule_id == "BR-KNOWLEDGE-REQUIRED"][0]
    assert br.applies is True


def test_evaluate_knowledge_not_required_for_greeting() -> None:
    context = _context_with_profile(profile={"customer_id": "c1"})
    intent = BusinessIntent(name="greeting")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    br = [c for c in result.constraints if c.rule_id == "BR-KNOWLEDGE-REQUIRED"][0]
    assert br.applies is False


def test_evaluate_is_feasible_true() -> None:
    context = _context_with_profile(profile={"customer_id": "c1"})
    intent = BusinessIntent(name="price_inquiry")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    assert result.is_feasible is True


def test_evaluate_is_feasible_false() -> None:
    context = _context_with_profile(profile={})
    intent = BusinessIntent(name="unknown")
    evaluator = RuleEvaluator()

    result = evaluator.evaluate(context, intent)

    assert result.is_feasible is False
