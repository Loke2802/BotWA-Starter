import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID

from app.core.automation.execution_monitor import ExecutionMonitor
from app.core.automation.task_registry import TaskRegistry
from app.domain.automation.contracts import (
    ExecutionPlan,
    ExecutionStatus,
    ExecutionStatusType,
    Task,
    TaskExecution,
    TaskExecutionStatus,
)


class TaskOrchestrator(ABC):
    @abstractmethod
    async def execute(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> ExecutionStatus: ...


class SequentialTaskOrchestrator(TaskOrchestrator):
    def __init__(
        self,
        registry: TaskRegistry,
        execution_monitor: ExecutionMonitor,
    ) -> None:
        self._registry = registry
        self._execution_monitor = execution_monitor

    async def execute(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> ExecutionStatus:
        tasks_map: dict[UUID, TaskExecution] = {}
        error_count = 0

        self._execution_monitor.on_start(plan, execution_id)

        sorted_tasks = sorted(plan.tasks, key=lambda t: t.order)

        for task in sorted_tasks:
            te = TaskExecution(task_id=task.task_id)
            tasks_map[task.task_id] = te

            self._execution_monitor.on_task_start(execution_id, task)

            result, error = await self._execute_with_retry(task)

            if error is None:
                te = te.model_copy(
                    update={
                        "status": TaskExecutionStatus.COMPLETED,
                        "completed_at": datetime.now(UTC),
                        "result_data": result or {},
                    },
                )
                tasks_map[task.task_id] = te
                self._execution_monitor.on_task_complete(execution_id, task)
            else:
                te = te.model_copy(
                    update={
                        "status": TaskExecutionStatus.FAILED,
                        "completed_at": datetime.now(UTC),
                        "error": error,
                    },
                )
                tasks_map[task.task_id] = te
                error_count += 1
                self._execution_monitor.on_task_failed(
                    execution_id,
                    task,
                    error,
                )

        final_status = (
            ExecutionStatusType.FAILED
            if error_count > 0
            else ExecutionStatusType.COMPLETED
        )
        status = ExecutionStatus(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            status=final_status,
            tasks=tasks_map,
            error_count=error_count,
            updated_at=datetime.now(UTC),
        )
        self._execution_monitor.on_complete(execution_id, final_status)
        return status

    async def _execute_with_retry(
        self,
        task: Task,
    ) -> tuple[dict[str, object] | None, str | None]:
        last_error: str | None = None
        max_attempts = task.retry_policy.max_attempts

        for attempt in range(1, max_attempts + 1):
            try:
                handler = self._registry.resolve(task.action)
                result = await handler.execute(task)
                return result, None
            except Exception as e:
                last_error = str(e)
                if attempt < max_attempts:
                    delay = task.retry_policy.delay_seconds * (
                        task.retry_policy.backoff_multiplier ** (attempt - 1)
                    )
                    await asyncio.sleep(delay)

        return None, last_error


class StubTaskOrchestrator(TaskOrchestrator):
    async def execute(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> ExecutionStatus:
        return ExecutionStatus(
            execution_id=execution_id,
            plan_id=plan.plan_id,
        )
