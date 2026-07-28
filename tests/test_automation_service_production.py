from unittest.mock import MagicMock
from uuid import UUID, uuid4

from app.core.automation.execution_monitor import StubExecutionMonitor
from app.core.automation.request_builder import (
    DefaultAutomationRequestBuilder,
)
from app.core.automation.service import AutomationService
from app.core.automation.task_orchestrator import StubTaskOrchestrator
from app.core.automation.task_registry import create_default_registry
from app.core.automation.workflow_planner import DefaultWorkflowPlanner
from app.domain.automation.metrics import AutomationMetrics
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


def test_get_metrics_without_db_returns_defaults() -> None:
    service = _make_service()
    metrics = service.get_metrics()
    assert isinstance(metrics, AutomationMetrics)
    assert metrics.total_executions == 0


def test_recover_without_db_returns_zero() -> None:
    service = _make_service()
    count = service.recover()
    assert count == 0


def test_idempotencia_without_db_executes_normally() -> None:
    service = _make_service()
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[ActionStep(action="respond", order=1)],
    )
    context = _make_context()

    execution_id = service.execute(decision, plan, context)

    assert isinstance(execution_id, UUID)


def test_service_with_session_factory_uses_production_path() -> None:
    mock_session = MagicMock()
    mock_session.close = MagicMock()
    mock_get_session = MagicMock()
    mock_get_session.side_effect = [
        iter([mock_session]),
        iter([mock_session]),
    ]

    registry = create_default_registry()
    service = AutomationService(
        request_builder=DefaultAutomationRequestBuilder(),
        workflow_planner=DefaultWorkflowPlanner(),
        task_orchestrator=StubTaskOrchestrator(),
        execution_monitor=StubExecutionMonitor(),
        registry=registry,
        session_factory=mock_get_session,
    )
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan(
        steps=[ActionStep(action="respond", order=1)],
    )
    context = _make_context()

    execution_id = service.execute(decision, plan, context)

    assert isinstance(execution_id, UUID)
