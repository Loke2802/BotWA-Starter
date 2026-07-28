from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.domain.automation.contracts import (
    AutomationRequest,
    AutomationResult,
    ExecutionPlan,
    ExecutionStatus,
    ExecutionStatusType,
    RetryPolicy,
    Task,
    TaskExecution,
    TaskExecutionStatus,
)
from app.domain.business.contracts import (
    BusinessActionPlan,
    BusinessContext,
    BusinessDecision,
    BusinessRequest,
)
from pydantic import ValidationError


def _make_request() -> BusinessRequest:
    return BusinessRequest(
        content="Test",
        customer_id="customer-1",
        company_id="company-1",
        conversation_id=uuid4(),
    )


def test_automation_request_fields() -> None:
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan()
    context = BusinessContext(request=_make_request())
    req = AutomationRequest(
        request_id=uuid4(),
        decision=decision,
        action_plan=plan,
        context=context,
    )
    assert req.decision.intent == "greeting"
    assert req.action_plan.total_steps == 0


def test_automation_request_generates_timestamp() -> None:
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan()
    context = BusinessContext(request=_make_request())
    req = AutomationRequest(
        request_id=uuid4(),
        decision=decision,
        action_plan=plan,
        context=context,
    )
    assert isinstance(req.created_at, datetime)
    assert req.created_at.tzinfo is UTC


def test_automation_request_is_frozen() -> None:
    decision = BusinessDecision(status="accepted", intent="greeting", confidence="high")
    plan = BusinessActionPlan()
    context = BusinessContext(request=_make_request())
    req = AutomationRequest(
        request_id=uuid4(),
        decision=decision,
        action_plan=plan,
        context=context,
    )
    with pytest.raises(ValidationError):
        req.decision = decision  # type: ignore[misc]


def test_retry_policy_defaults() -> None:
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.delay_seconds == 1.0
    assert policy.backoff_multiplier == 2.0


def test_task_fields() -> None:
    task = Task(
        task_id=uuid4(),
        action="send_email",
        target="customer@example.com",
        parameters={"template": "welcome"},
        order=1,
    )
    assert task.action == "send_email"
    assert task.target == "customer@example.com"
    assert task.parameters == {"template": "welcome"}
    assert task.order == 1


def test_task_defaults_retry_policy() -> None:
    task = Task(task_id=uuid4(), action="respond")
    assert isinstance(task.retry_policy, RetryPolicy)
    assert task.timeout_seconds == 30.0


def test_execution_plan_fields() -> None:
    plan_id = uuid4()
    request_id = uuid4()
    task = Task(task_id=uuid4(), action="respond")
    plan = ExecutionPlan(plan_id=plan_id, request_id=request_id, tasks=[task])
    assert plan.plan_id == plan_id
    assert plan.request_id == request_id
    assert len(plan.tasks) == 1


def test_execution_status_type_values() -> None:
    assert ExecutionStatusType.PENDING.value == "pending"
    assert ExecutionStatusType.RUNNING.value == "running"
    assert ExecutionStatusType.COMPLETED.value == "completed"
    assert ExecutionStatusType.FAILED.value == "failed"
    assert ExecutionStatusType.CANCELLED.value == "cancelled"


def test_task_execution_status_values() -> None:
    assert TaskExecutionStatus.PENDING.value == "pending"
    assert TaskExecutionStatus.RUNNING.value == "running"
    assert TaskExecutionStatus.COMPLETED.value == "completed"
    assert TaskExecutionStatus.FAILED.value == "failed"
    assert TaskExecutionStatus.RETRYING.value == "retrying"
    assert TaskExecutionStatus.SKIPPED.value == "skipped"


def test_task_execution_defaults() -> None:
    task_id = uuid4()
    te = TaskExecution(task_id=task_id)
    assert te.task_id == task_id
    assert te.status == TaskExecutionStatus.PENDING
    assert te.attempt == 0
    assert te.started_at is None
    assert te.completed_at is None
    assert te.error is None
    assert te.result_data == {}


def test_execution_status_defaults() -> None:
    execution_id = uuid4()
    plan_id = uuid4()
    status = ExecutionStatus(execution_id=execution_id, plan_id=plan_id)
    assert status.execution_id == execution_id
    assert status.plan_id == plan_id
    assert status.status == ExecutionStatusType.PENDING
    assert status.tasks == {}
    assert status.error_count == 0


def test_automation_result_fields() -> None:
    execution_id = uuid4()
    now = datetime.now(UTC)
    result = AutomationResult(
        execution_id=execution_id,
        status=ExecutionStatusType.COMPLETED,
        completed_tasks=[uuid4()],
        failed_tasks=[],
        errors=[],
        duration_ms=1500,
        result_data={"key": "value"},
        finished_at=now,
    )
    assert result.execution_id == execution_id
    assert result.status == ExecutionStatusType.COMPLETED
    assert len(result.completed_tasks) == 1
    assert result.duration_ms == 1500
    assert result.result_data == {"key": "value"}
    assert result.finished_at == now
