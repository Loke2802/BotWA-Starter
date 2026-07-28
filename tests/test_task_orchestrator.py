from uuid import uuid4

import pytest
from app.core.automation.execution_monitor import StubExecutionMonitor
from app.core.automation.task_orchestrator import (
    SequentialTaskOrchestrator,
    TaskOrchestrator,
)
from app.core.automation.task_registry import (
    RespondHandler,
    TaskRegistry,
    create_default_registry,
)
from app.domain.automation.contracts import (
    ExecutionPlan,
    ExecutionStatusType,
    Task,
    TaskExecutionStatus,
)


@pytest.mark.asyncio
async def test_orchestrator_implements_abc() -> None:
    registry = create_default_registry()
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)
    assert isinstance(orch, TaskOrchestrator)


@pytest.mark.asyncio
async def test_orchestrator_executes_single_task() -> None:
    registry = TaskRegistry()
    registry.register("respond", RespondHandler())
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    task = Task(task_id=uuid4(), action="respond", order=0)
    plan = ExecutionPlan(
        plan_id=uuid4(),
        request_id=uuid4(),
        tasks=[task],
    )
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.COMPLETED
    assert status.error_count == 0
    assert len(status.tasks) == 1
    te = status.tasks[task.task_id]
    assert te.status == TaskExecutionStatus.COMPLETED


@pytest.mark.asyncio
async def test_orchestrator_executes_tasks_in_order() -> None:
    registry = create_default_registry()
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    t1 = Task(task_id=uuid4(), action="respond", order=2)
    t2 = Task(task_id=uuid4(), action="respond", order=0)
    t3 = Task(task_id=uuid4(), action="respond", order=1)

    plan = ExecutionPlan(
        plan_id=uuid4(),
        request_id=uuid4(),
        tasks=[t1, t2, t3],
    )
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.COMPLETED
    task_ids = list(status.tasks.keys())
    assert task_ids == [t2.task_id, t3.task_id, t1.task_id]


@pytest.mark.asyncio
async def test_orchestrator_reports_failed_task() -> None:
    registry = TaskRegistry()
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    task = Task(task_id=uuid4(), action="nonexistent", order=0)
    plan = ExecutionPlan(
        plan_id=uuid4(),
        request_id=uuid4(),
        tasks=[task],
    )
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.FAILED
    assert status.error_count == 1
    te = status.tasks[task.task_id]
    assert te.status == TaskExecutionStatus.FAILED
    assert te.error is not None


@pytest.mark.asyncio
async def test_orchestrator_empty_plan() -> None:
    registry = create_default_registry()
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    plan = ExecutionPlan(plan_id=uuid4(), request_id=uuid4())
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.COMPLETED
    assert status.error_count == 0
    assert len(status.tasks) == 0


@pytest.mark.asyncio
async def test_orchestrator_retry_on_failure() -> None:
    call_count = 0

    class FailingHandler:
        async def execute(self, task: Task) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient error")
            return {"status": "completed"}

    registry = TaskRegistry()
    registry.register("flaky", FailingHandler())  # type: ignore[arg-type]
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    task = Task(
        task_id=uuid4(),
        action="flaky",
        order=0,
    )
    plan = ExecutionPlan(
        plan_id=uuid4(),
        request_id=uuid4(),
        tasks=[task],
    )
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.COMPLETED
    assert call_count == 3


@pytest.mark.asyncio
async def test_orchestrator_exhausts_retries() -> None:
    class AlwaysFailsHandler:
        async def execute(self, task: Task) -> dict[str, object]:
            raise RuntimeError("Always fails")

    registry = TaskRegistry()
    registry.register("broken", AlwaysFailsHandler())  # type: ignore[arg-type]
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    task = Task(
        task_id=uuid4(),
        action="broken",
        order=0,
    )
    plan = ExecutionPlan(
        plan_id=uuid4(),
        request_id=uuid4(),
        tasks=[task],
    )
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.FAILED
    te = status.tasks[task.task_id]
    assert te.status == TaskExecutionStatus.FAILED
    assert "Always fails" in (te.error or "")


@pytest.mark.asyncio
async def test_orchestrator_partial_failure() -> None:
    registry = TaskRegistry()
    registry.register("respond", RespondHandler())
    monitor = StubExecutionMonitor()
    orch = SequentialTaskOrchestrator(registry, monitor)

    t1 = Task(task_id=uuid4(), action="respond", order=0)
    t2 = Task(task_id=uuid4(), action="nonexistent", order=1)
    t3 = Task(task_id=uuid4(), action="respond", order=2)

    plan = ExecutionPlan(
        plan_id=uuid4(),
        request_id=uuid4(),
        tasks=[t1, t2, t3],
    )
    execution_id = uuid4()

    status = await orch.execute(plan, execution_id)

    assert status.status == ExecutionStatusType.FAILED
    assert status.error_count == 1
    assert status.tasks[t1.task_id].status == TaskExecutionStatus.COMPLETED
    assert status.tasks[t2.task_id].status == TaskExecutionStatus.FAILED
    assert status.tasks[t3.task_id].status == TaskExecutionStatus.COMPLETED
