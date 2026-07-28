from uuid import UUID, uuid4

from app.core.automation.execution_monitor import StubExecutionMonitor
from app.core.automation.request_builder import (
    DefaultAutomationRequestBuilder,
)
from app.core.automation.service import AutomationService
from app.core.automation.task_orchestrator import StubTaskOrchestrator
from app.core.automation.workflow_planner import DefaultWorkflowPlanner
from app.domain.automation.contracts import (
    AutomationRequest,
    ExecutionPlan,
)
from app.domain.business.contracts import (
    ActionStep,
    BusinessActionPlan,
    BusinessContext,
    BusinessDecision,
    BusinessRequest,
)


def _make_service() -> AutomationService:
    return AutomationService(
        request_builder=DefaultAutomationRequestBuilder(),
        workflow_planner=DefaultWorkflowPlanner(),
        task_orchestrator=StubTaskOrchestrator(),
        execution_monitor=StubExecutionMonitor(),
    )


def _make_context() -> BusinessContext:
    return BusinessContext(
        request=BusinessRequest(
            content="Test",
            customer_id="customer-1",
            company_id="company-1",
            conversation_id=uuid4(),
        ),
    )


def test_service_execute_returns_uuid() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[ActionStep(action="respond", order=1)],
    )
    context = _make_context()

    execution_id = service.execute(decision, plan, context)

    assert isinstance(execution_id, UUID)


def test_service_stores_last_request() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[ActionStep(action="respond", order=1)],
    )
    context = _make_context()

    service.execute(decision, plan, context)

    assert isinstance(service._last_request, AutomationRequest)
    assert service._last_request.decision.intent == "greeting"


def test_service_stores_last_execution_plan() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[ActionStep(action="respond", order=1)],
    )
    context = _make_context()

    service.execute(decision, plan, context)

    ep = service._last_execution_plan
    assert isinstance(ep, ExecutionPlan)
    assert len(ep.tasks) == 1
    assert ep.tasks[0].action == "respond"


def test_service_execute_with_custom_execution_id() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[ActionStep(action="respond", order=1)],
    )
    context = _make_context()
    custom_id = uuid4()

    execution_id = service.execute(decision, plan, context, execution_id=custom_id)

    assert execution_id == custom_id
    assert service._last_execution_id == custom_id


def test_service_execute_with_empty_plan() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan()
    context = _make_context()

    execution_id = service.execute(decision, plan, context)

    assert isinstance(execution_id, UUID)
    ep = service._last_execution_plan
    assert ep is not None
    assert len(ep.tasks) == 0


def test_service_execute_with_multiple_steps() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[
            ActionStep(action="respond", order=1),
            ActionStep(action="log", order=2),
        ],
    )
    context = _make_context()

    execution_id = service.execute(decision, plan, context)

    assert isinstance(execution_id, UUID)
    ep = service._last_execution_plan
    assert ep is not None
    assert len(ep.tasks) == 2
    assert ep.tasks[0].action == "respond"
    assert ep.tasks[1].action == "log"


def test_service_execute_maps_parameters() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[
            ActionStep(
                action="send_email",
                target="user@test.com",
                parameters={"template": "welcome"},
                order=1,
            ),
        ],
    )
    context = _make_context()

    service.execute(decision, plan, context)

    ep = service._last_execution_plan
    assert ep is not None
    task = ep.tasks[0]
    assert task.action == "send_email"
    assert task.target == "user@test.com"
    assert task.parameters == {"template": "welcome"}
    assert task.order == 1
