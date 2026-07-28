from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import uuid4

from app.domain.automation.contracts import (
    AutomationRequest,
    ExecutionPlan,
    Task,
)


class WorkflowPlanner(ABC):
    @abstractmethod
    def plan(
        self,
        request: AutomationRequest,
    ) -> ExecutionPlan: ...


class DefaultWorkflowPlanner(WorkflowPlanner):
    def plan(
        self,
        request: AutomationRequest,
    ) -> ExecutionPlan:
        tasks: list[Task] = []
        for step in request.action_plan.steps:
            task = Task(
                task_id=uuid4(),
                action=step.action,
                target=step.target,
                parameters=step.parameters,
                order=step.order,
            )
            tasks.append(task)
        return ExecutionPlan(
            plan_id=uuid4(),
            request_id=request.request_id,
            tasks=tasks,
            created_at=datetime.now(UTC),
        )
