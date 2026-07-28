from uuid import uuid4

from app.core.automation.execution_monitor import (
    ExecutionMonitor,
    StubExecutionMonitor,
    WorkflowExecutionMonitor,
)
from app.domain.automation.contracts import (
    AutomationResult,
    ExecutionPlan,
    ExecutionStatusType,
    Task,
)


def test_workflow_monitor_implements_abc() -> None:
    monitor = WorkflowExecutionMonitor()
    assert isinstance(monitor, ExecutionMonitor)


def test_stub_monitor_implements_abc() -> None:
    monitor = StubExecutionMonitor()
    assert isinstance(monitor, ExecutionMonitor)


def test_workflow_monitor_on_start_does_not_crash() -> None:
    monitor = WorkflowExecutionMonitor()
    plan = ExecutionPlan(plan_id=uuid4(), request_id=uuid4())
    monitor.on_start(plan, uuid4())


def test_workflow_monitor_on_task_events_do_not_crash() -> None:
    monitor = WorkflowExecutionMonitor()
    execution_id = uuid4()
    task = Task(task_id=uuid4(), action="respond")
    monitor.on_task_start(execution_id, task)
    monitor.on_task_complete(execution_id, task)
    monitor.on_task_failed(execution_id, task, "error")


def test_workflow_monitor_on_complete_returns_result() -> None:
    monitor = WorkflowExecutionMonitor()
    execution_id = uuid4()
    result = monitor.on_complete(execution_id, ExecutionStatusType.COMPLETED)
    assert isinstance(result, AutomationResult)
    assert result.execution_id == execution_id
    assert result.status == ExecutionStatusType.COMPLETED


def test_workflow_monitor_stores_result() -> None:
    monitor = WorkflowExecutionMonitor()
    execution_id = uuid4()
    monitor.on_complete(execution_id, ExecutionStatusType.FAILED)
    stored = monitor.get_result(execution_id)
    assert stored is not None
    assert stored.status == ExecutionStatusType.FAILED


def test_workflow_monitor_get_result_none_for_unknown() -> None:
    monitor = WorkflowExecutionMonitor()
    result = monitor.get_result(uuid4())
    assert result is None


def test_workflow_monitor_multiple_executions() -> None:
    monitor = WorkflowExecutionMonitor()
    id1 = uuid4()
    id2 = uuid4()
    monitor.on_complete(id1, ExecutionStatusType.COMPLETED)
    monitor.on_complete(id2, ExecutionStatusType.FAILED)
    r1 = monitor.get_result(id1)
    r2 = monitor.get_result(id2)
    assert r1 is not None
    assert r1.status == ExecutionStatusType.COMPLETED
    assert r2 is not None
    assert r2.status == ExecutionStatusType.FAILED


def test_stub_monitor_on_complete_returns_result() -> None:
    monitor = StubExecutionMonitor()
    execution_id = uuid4()
    result = monitor.on_complete(execution_id, ExecutionStatusType.COMPLETED)
    assert isinstance(result, AutomationResult)
    assert result.execution_id == execution_id
