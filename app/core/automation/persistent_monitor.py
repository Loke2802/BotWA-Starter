from datetime import UTC, datetime
from uuid import UUID

from app.core.automation.event_publisher import AutomationEventPublisher
from app.core.automation.execution_monitor import ExecutionMonitor
from app.domain.automation.contracts import (
    AutomationResult,
    ExecutionPlan,
    ExecutionStatusType,
    Task,
)
from app.infrastructure.models.automation_execution import (
    AutomationExecutionModel,
)
from app.infrastructure.models.automation_task_execution import (
    AutomationTaskExecutionModel,
)
from app.infrastructure.repositories.automation_execution_repository import (
    AutomationExecutionRepository,
)
from app.infrastructure.repositories.automation_task_execution_repository import (
    AutomationTaskExecutionRepository,
)


class PersistentExecutionMonitor(ExecutionMonitor):
    def __init__(
        self,
        execution_repo: AutomationExecutionRepository,
        task_execution_repo: AutomationTaskExecutionRepository,
        event_publisher: AutomationEventPublisher,
    ) -> None:
        self._execution_repo = execution_repo
        self._task_execution_repo = task_execution_repo
        self._event_publisher = event_publisher

    def on_start(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> None:
        now = datetime.now(UTC)
        model = AutomationExecutionModel(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            status="running",
            started_at=now,
            updated_at=now,
            total_tasks=len(plan.tasks),
        )
        self._execution_repo.add(model)
        self._event_publisher.publish(
            "automation.execution.started",
            execution_id,
            plan_id=str(plan.plan_id),
        )

    def on_task_start(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None:
        now = datetime.now(UTC)
        model = AutomationTaskExecutionModel(
            execution_id=execution_id,
            task_id=task.task_id,
            action=task.action,
            order=task.order,
            status="running",
            started_at=now,
        )
        self._task_execution_repo.add(model)
        self._event_publisher.publish(
            "automation.task.started",
            execution_id,
            task_id=str(task.task_id),
            action=task.action,
        )

    def on_task_complete(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None:
        records = self._task_execution_repo.list_by_execution(execution_id)
        for record in records:
            if record.task_id == task.task_id:
                record.status = "completed"
                record.completed_at = datetime.now(UTC)
                self._task_execution_repo.update(record)
                break
        self._update_execution_counts(execution_id)
        self._event_publisher.publish(
            "automation.task.completed",
            execution_id,
            task_id=str(task.task_id),
        )

    def on_task_failed(
        self,
        execution_id: UUID,
        task: Task,
        error: str,
    ) -> None:
        records = self._task_execution_repo.list_by_execution(execution_id)
        for record in records:
            if record.task_id == task.task_id:
                record.status = "failed"
                record.completed_at = datetime.now(UTC)
                record.error = error
                self._task_execution_repo.update(record)
                break
        self._update_execution_counts(execution_id)
        self._event_publisher.publish(
            "automation.task.failed",
            execution_id,
            task_id=str(task.task_id),
            error_code="UNEXPECTED_ERROR",
        )

    def on_complete(
        self,
        execution_id: UUID,
        status: ExecutionStatusType,
    ) -> AutomationResult:
        model = self._execution_repo.get(execution_id)
        if model is not None:
            model.status = status.value
            model.finished_at = datetime.now(UTC)
            model.updated_at = datetime.now(UTC)
            self._update_execution_counts(execution_id)
            self._execution_repo.update(model)

        event_type = f"automation.execution.{status.value}"
        self._event_publisher.publish(event_type, execution_id)

        return AutomationResult(
            execution_id=execution_id,
            status=status,
            finished_at=datetime.now(UTC),
        )

    def get_execution(
        self,
        execution_id: UUID,
    ) -> AutomationExecutionModel | None:
        return self._execution_repo.get(execution_id)

    def list_running(self) -> list[AutomationExecutionModel]:
        return self._execution_repo.list_by_status("running")

    def list_failed(self) -> list[AutomationExecutionModel]:
        return self._execution_repo.list_by_status("failed")

    def list_completed(self) -> list[AutomationExecutionModel]:
        return self._execution_repo.list_by_status("completed")

    def _update_execution_counts(
        self,
        execution_id: UUID,
    ) -> None:
        model = self._execution_repo.get(execution_id)
        if model is None:
            return
        all_tasks = self._task_execution_repo.list_by_execution(execution_id)
        model.completed_tasks = sum(1 for t in all_tasks if t.status == "completed")
        model.failed_tasks = sum(1 for t in all_tasks if t.status == "failed")
        model.error_count = model.failed_tasks
        model.updated_at = datetime.now(UTC)
