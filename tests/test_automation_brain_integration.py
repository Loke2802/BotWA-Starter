from uuid import uuid4

from app.core.automation.execution_monitor import StubExecutionMonitor
from app.core.automation.request_builder import (
    DefaultAutomationRequestBuilder,
)
from app.core.automation.service import AutomationService
from app.core.automation.task_orchestrator import StubTaskOrchestrator
from app.core.automation.workflow_planner import DefaultWorkflowPlanner
from app.core.business.action_planner import ActionPlanner
from app.core.business.confidence_evaluator import ConfidenceEvaluator
from app.core.business.context_interpreter import ContextInterpreter
from app.core.business.customer_profile_provider import (
    InMemoryCustomerProfileProvider,
)
from app.core.business.decision_maker import DecisionMaker
from app.core.business.event_publisher import BusinessEventPublisher
from app.core.business.intent_classifier import IntentClassifier
from app.core.business.rule_evaluator import RuleEvaluator
from app.core.business.service import BusinessBrainService
from app.domain.business.contracts import BusinessRequest


def _make_bb_service(
    automation_service: AutomationService | None = None,
) -> BusinessBrainService:
    profile_provider = InMemoryCustomerProfileProvider()
    return BusinessBrainService(
        intent_classifier=IntentClassifier(),
        context_interpreter=ContextInterpreter(
            customer_profile_provider=profile_provider,
        ),
        rule_evaluator=RuleEvaluator(),
        decision_maker=DecisionMaker(),
        confidence_evaluator=ConfidenceEvaluator(),
        action_planner=ActionPlanner(),
        event_publisher=BusinessEventPublisher(),
        automation_service=automation_service,
    )


def test_brain_invokes_automation_for_greeting() -> None:
    automation_service = AutomationService(
        request_builder=DefaultAutomationRequestBuilder(),
        workflow_planner=DefaultWorkflowPlanner(),
        task_orchestrator=StubTaskOrchestrator(),
        execution_monitor=StubExecutionMonitor(),
    )
    bb = _make_bb_service(automation_service)
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    bb.process(request)

    assert automation_service._last_execution_plan is not None
    assert len(automation_service._last_execution_plan.tasks) >= 1
    assert automation_service._last_request is not None
    assert automation_service._last_request.decision.intent == "greeting"


def test_brain_without_automation_service_does_not_crash() -> None:
    bb = _make_bb_service(automation_service=None)
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = bb.process(request)

    assert decision.intent == "greeting"
    assert decision.status == "accepted"


def test_brain_automation_compatible_with_none_action_planner() -> None:
    automation_service = AutomationService(
        request_builder=DefaultAutomationRequestBuilder(),
        workflow_planner=DefaultWorkflowPlanner(),
        task_orchestrator=StubTaskOrchestrator(),
        execution_monitor=StubExecutionMonitor(),
    )
    bb = BusinessBrainService(
        intent_classifier=IntentClassifier(),
        automation_service=automation_service,
    )
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    decision = bb.process(request)

    assert decision.intent == "greeting"
    assert automation_service._last_execution_plan is None


def test_automation_receives_same_execution_id_as_request_id() -> None:
    automation_service = AutomationService(
        request_builder=DefaultAutomationRequestBuilder(),
        workflow_planner=DefaultWorkflowPlanner(),
        task_orchestrator=StubTaskOrchestrator(),
        execution_monitor=StubExecutionMonitor(),
    )
    bb = _make_bb_service(automation_service)
    request = BusinessRequest(
        content="Hola",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )

    bb.process(request)

    assert automation_service._last_request is not None
    assert automation_service._last_execution_id is not None
    last_req = automation_service._last_request
    assert automation_service._last_execution_id == last_req.request_id
    assert automation_service._last_execution_plan is not None
    assert automation_service._last_execution_plan.request_id == last_req.request_id
