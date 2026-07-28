from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID

from app.domain.automation.contracts import (
    AutomationResult,
    ExecutionPlan,
    ExecutionStatusType,
    Task,
)


class ExecutionMonitor(ABC):
    @abstractmethod
    def on_start(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> None: ...

    @abstractmethod
    def on_task_start(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None: ...

    @abstractmethod
    def on_task_complete(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None: ...

    @abstractmethod
    def on_task_failed(
        self,
        execution_id: UUID,
        task: Task,
        error: str,
    ) -> None: ...

    @abstractmethod
    def on_complete(
        self,
        execution_id: UUID,
        status: ExecutionStatusType,
    ) -> AutomationResult: ...


class WorkflowExecutionMonitor(ExecutionMonitor):
    def __init__(self) -> None:
        self._results: dict[UUID, AutomationResult] = {}

    def on_start(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> None:
        pass

    def on_task_start(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None:
        pass

    def on_task_complete(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None:
        pass

    def on_task_failed(
        self,
        execution_id: UUID,
        task: Task,
        error: str,
    ) -> None:
        pass

    def on_complete(
        self,
        execution_id: UUID,
        status: ExecutionStatusType,
    ) -> AutomationResult:
        result = AutomationResult(
            execution_id=execution_id,
            status=status,
            finished_at=datetime.now(UTC),
        )
        self._results[execution_id] = result
        return result

    def get_result(self, execution_id: UUID) -> AutomationResult | None:
        return self._results.get(execution_id)


class StubExecutionMonitor(ExecutionMonitor):
    def on_start(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> None:
        pass

    def on_task_start(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None:
        pass

    def on_task_complete(
        self,
        execution_id: UUID,
        task: Task,
    ) -> None:
        pass

    def on_task_failed(
        self,
        execution_id: UUID,
        task: Task,
        error: str,
    ) -> None:
        pass

    def on_complete(
        self,
        execution_id: UUID,
        status: ExecutionStatusType,
    ) -> AutomationResult:
        return AutomationResult(
            execution_id=execution_id,
            status=status,
            finished_at=datetime.now(UTC),
        )
