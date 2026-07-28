from typing import cast
from uuid import uuid4

from app.core.business.event_publisher import BusinessEventPublisher
from app.domain.business.contracts import (
    ActionStep,
    BusinessActionPlan,
    BusinessConstraint,
    BusinessConstraints,
    BusinessContext,
    BusinessDecision,
    BusinessEvent,
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


def _feasible() -> BusinessConstraints:
    return BusinessConstraints(is_feasible=True)


def _not_feasible() -> BusinessConstraints:
    return BusinessConstraints(
        constraints=[
            BusinessConstraint(
                rule_id="BR-INTENT-KNOWN",
                description="Intent known",
                applies=True,
                reason="intent_not_recognized",
            ),
        ],
        is_feasible=False,
    )


def _decision(
    intent: str = "greeting",
    status: str = "accepted",
    confidence: str = "high",
    needs_knowledge: bool = False,
    knowledge_content: str | None = None,
) -> BusinessDecision:
    return BusinessDecision(
        status=status,
        intent=intent,
        confidence=confidence,
        needs_knowledge=needs_knowledge,
        knowledge_content=knowledge_content,
    )


def _respond_plan() -> BusinessActionPlan:
    return BusinessActionPlan(
        steps=[ActionStep(action="respond", target="conversation_service", order=1)],
        total_steps=1,
    )


def _escalate_plan() -> BusinessActionPlan:
    return BusinessActionPlan(
        steps=[ActionStep(action="escalate", target="human_support", order=1)],
        total_steps=1,
    )


class TestEventPublisherGreeting:
    def test_publishes_three_events(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        assert len(events) == 3

    def test_event_types(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        assert events[0].event_type == "business_intent.detected"
        assert events[1].event_type == "business_decision.made"
        assert events[2].event_type == "business_action.plan"

    def test_event_source(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        for event in events:
            assert event.source == "business_brain"

    def test_events_have_conversation_id(self) -> None:
        conv_id = uuid4()
        context = BusinessContext(
            request=BusinessRequest(
                content="Hola",
                customer_id="customer-1",
                company_id="company-1",
                conversation_id=conv_id,
            ),
            intent="greeting",
        )
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            context,
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        for event in events:
            assert event.conversation_id == conv_id


class TestEventPublisherPriceInquiry:
    def _plan_with_two_steps(self) -> BusinessActionPlan:
        return BusinessActionPlan(
            steps=[
                ActionStep(
                    action="query_knowledge",
                    target="knowledge_service",
                    order=1,
                ),
                ActionStep(
                    action="respond",
                    target="conversation_service",
                    order=2,
                ),
            ],
            total_steps=2,
        )

    def test_with_knowledge_publishes_four_events(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("price_inquiry"),
            _intent("price_inquiry"),
            _feasible(),
            _decision(
                "price_inquiry",
                needs_knowledge=True,
                knowledge_content="Some info",
            ),
            _respond_plan(),
        )
        assert len(events) == 4
        assert events[2].event_type == "knowledge.queried"
        assert events[2].payload["found"] is True

    def test_without_knowledge_found_is_false(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("price_inquiry"),
            _intent("price_inquiry"),
            _feasible(),
            _decision(
                "price_inquiry",
                needs_knowledge=True,
                knowledge_content=None,
            ),
            self._plan_with_two_steps(),
        )
        assert len(events) == 4
        assert events[2].event_type == "knowledge.queried"
        assert events[2].payload["found"] is False

    def test_without_needs_knowledge_has_three_events(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("price_inquiry"),
            _intent("price_inquiry"),
            _feasible(),
            _decision("price_inquiry", needs_knowledge=False),
            _respond_plan(),
        )
        assert len(events) == 3


class TestEventPublisherUnknown:
    def test_rejected_publishes_three_events(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("unknown"),
            _intent("unknown"),
            _not_feasible(),
            _decision("unknown", status="rejected"),
            _escalate_plan(),
        )
        assert len(events) == 3

    def test_rejected_has_rejected_in_payload(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("unknown"),
            _intent("unknown"),
            _not_feasible(),
            _decision("unknown", status="rejected", confidence="low"),
            _escalate_plan(),
        )
        assert events[1].payload["status"] == "rejected"
        assert events[1].payload["confidence"] == "low"
        assert events[1].payload["is_feasible"] is False

    def test_action_plan_contains_steps(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("unknown"),
            _intent("unknown"),
            _not_feasible(),
            _decision("unknown", status="rejected", confidence="low"),
            _escalate_plan(),
        )
        action_event = events[2]
        steps = cast(list[dict[str, object]], action_event.payload.get("steps", []))
        assert len(steps) == 1
        assert steps[0].get("action") == "escalate"
        assert steps[0].get("target") == "human_support"
        assert steps[0].get("order") == 1

    def test_action_plan_empty_when_none(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            None,
        )
        action_event = events[2]
        assert action_event.payload["steps"] == []
        assert action_event.payload["total_steps"] == 0


class TestEventPublisherEdgeCases:
    def test_events_are_frozen(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        for event in events:
            assert isinstance(event, BusinessEvent)

    def test_events_have_timestamp(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        for event in events:
            assert event.timestamp is not None

    def test_no_repo_still_returns_events(self) -> None:
        publisher = BusinessEventPublisher()
        events = publisher.publish_events(
            _context("greeting"),
            _intent("greeting"),
            _feasible(),
            _decision("greeting"),
            _respond_plan(),
        )
        assert len(events) == 3
