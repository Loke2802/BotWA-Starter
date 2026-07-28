from uuid import uuid4

import pytest
from app.core.business.action_planner import ActionPlanner
from app.domain.business.contracts import (
    BusinessConstraint,
    BusinessConstraints,
    BusinessContext,
    BusinessDecision,
    BusinessIntent,
    BusinessRequest,
)


def _context(intent: str = "greeting") -> BusinessContext:
    return BusinessContext(
        request=BusinessRequest(
            content="Hola",
            customer_id="customer-1",
            company_id="company-1",
            conversation_id=uuid4(),
        ),
        intent=intent,
    )


def _intent(name: str) -> BusinessIntent:
    return BusinessIntent(name=name)


def _feasible_constraints() -> BusinessConstraints:
    return BusinessConstraints(
        constraints=[
            BusinessConstraint(
                rule_id="BR-INTENT-KNOWN",
                description="Intent known",
                applies=False,
            ),
            BusinessConstraint(
                rule_id="BR-CUSTOMER-ACTIVE",
                description="Customer active",
                applies=False,
            ),
            BusinessConstraint(
                rule_id="BR-KNOWLEDGE-REQUIRED",
                description="Knowledge required",
                applies=False,
            ),
        ],
        is_feasible=True,
    )


def _not_feasible_constraints(
    reason: str = "intent_not_recognized",
) -> BusinessConstraints:
    return BusinessConstraints(
        constraints=[
            BusinessConstraint(
                rule_id="BR-INTENT-KNOWN",
                description="Intent known",
                applies=True,
                reason=reason,
            ),
        ],
        is_feasible=False,
    )


def _decision(
    intent: str = "greeting",
    status: str = "accepted",
    needs_knowledge: bool = False,
    knowledge_content: str | None = None,
) -> BusinessDecision:
    return BusinessDecision(
        status=status,
        intent=intent,
        confidence="high",
        needs_knowledge=needs_knowledge,
        knowledge_content=knowledge_content,
    )


class TestActionPlannerGreeting:
    def test_greeting_plan_has_respond(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("greeting"),
            _intent("greeting"),
            _feasible_constraints(),
            _decision("greeting"),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "respond"
        assert plan.steps[0].target == "conversation_service"

    def test_greeting_plan_parameters(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("greeting"),
            _intent("greeting"),
            _feasible_constraints(),
            _decision("greeting"),
        )
        assert plan.steps[0].parameters["intent"] == "greeting"
        assert plan.steps[0].parameters["content"] == "Hola"


class TestActionPlannerFarewell:
    def test_farewell_plan(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("farewell"),
            _intent("farewell"),
            _feasible_constraints(),
            _decision("farewell"),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "respond"


class TestActionPlannerThanks:
    def test_thanks_plan(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("thanks"),
            _intent("thanks"),
            _feasible_constraints(),
            _decision("thanks"),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "respond"


class TestActionPlannerPriceInquiry:
    def test_price_inquiry_without_knowledge_has_two_steps(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("price_inquiry"),
            _intent("price_inquiry"),
            _feasible_constraints(),
            _decision("price_inquiry", needs_knowledge=True, knowledge_content=None),
        )
        assert plan.total_steps == 2
        assert plan.steps[0].action == "query_knowledge"
        assert plan.steps[0].target == "knowledge_service"
        assert plan.steps[1].action == "respond"
        assert plan.steps[1].target == "conversation_service"

    def test_price_inquiry_with_knowledge_has_one_step(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("price_inquiry"),
            _intent("price_inquiry"),
            _feasible_constraints(),
            _decision(
                "price_inquiry",
                needs_knowledge=True,
                knowledge_content="Some info",
            ),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "respond"


class TestActionPlannerSupport:
    def test_support_without_knowledge_has_two_steps(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("support"),
            _intent("support"),
            _feasible_constraints(),
            _decision("support", needs_knowledge=True, knowledge_content=None),
        )
        assert plan.total_steps == 2
        assert plan.steps[0].action == "query_knowledge"
        assert plan.steps[1].action == "respond"

    def test_support_with_knowledge_has_one_step(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("support"),
            _intent("support"),
            _feasible_constraints(),
            _decision(
                "support",
                needs_knowledge=True,
                knowledge_content="Some info",
            ),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "respond"


class TestActionPlannerQuestion:
    def test_question_without_knowledge_has_two_steps(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("question"),
            _intent("question"),
            _feasible_constraints(),
            _decision("question", needs_knowledge=True, knowledge_content=None),
        )
        assert plan.total_steps == 2
        assert plan.steps[0].action == "query_knowledge"
        assert plan.steps[1].action == "respond"

    def test_question_with_knowledge_has_one_step(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("question"),
            _intent("question"),
            _feasible_constraints(),
            _decision(
                "question",
                needs_knowledge=True,
                knowledge_content="Some info",
            ),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "respond"


class TestActionPlannerUnknown:
    def test_unknown_not_feasible_plan_is_escalate(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("unknown"),
            _intent("unknown"),
            _not_feasible_constraints(),
            _decision("unknown", status="rejected"),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "escalate"
        assert plan.steps[0].target == "human_support"
        reason: str = str(plan.steps[0].parameters.get("reason", ""))
        assert "intent_not_recognized" in reason


class TestActionPlannerFeasibilityOverride:
    def test_not_feasible_greeting_plan_is_escalate(self) -> None:
        planner = ActionPlanner()
        plan = planner.plan(
            _context("greeting"),
            _intent("greeting"),
            _not_feasible_constraints("customer_inactive"),
            _decision("greeting", status="rejected"),
        )
        assert plan.total_steps == 1
        assert plan.steps[0].action == "escalate"
        assert plan.steps[0].parameters["reason"] == "customer_inactive"


class TestActionPlannerEdgeCases:
    @pytest.mark.parametrize(
        "intent_name",
        [
            "greeting",
            "farewell",
            "thanks",
            "question",
            "support",
            "price_inquiry",
            "unknown",
        ],
    )
    def test_all_known_intents_have_at_least_one_step(self, intent_name: str) -> None:
        planner = ActionPlanner()
        needs_knowledge = intent_name in ("question", "support", "price_inquiry")
        plan = planner.plan(
            _context(intent_name),
            _intent(intent_name),
            _feasible_constraints(),
            _decision(intent_name, needs_knowledge=needs_knowledge),
        )
        assert plan.total_steps >= 1
