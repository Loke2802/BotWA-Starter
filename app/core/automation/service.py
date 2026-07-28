import asyncio
import threading
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.automation.event_publisher import AutomationEventPublisher
from app.core.automation.execution_monitor import ExecutionMonitor
from app.core.automation.persistent_monitor import PersistentExecutionMonitor
from app.core.automation.request_builder import AutomationRequestBuilder
from app.core.automation.task_orchestrator import (
    SequentialTaskOrchestrator,
    TaskOrchestrator,
)
from app.core.automation.task_registry import TaskRegistry
from app.core.automation.workflow_planner import WorkflowPlanner
from app.domain.automation.contracts import (
    AutomationRequest,
    ExecutionPlan,
)
from app.domain.automation.metrics import AutomationMetrics
from app.domain.business.contracts import (
    BusinessActionPlan,
    BusinessContext,
    BusinessDecision,
)
from app.infrastructure.repositories.automation_execution_repository import (
    AutomationExecutionRepository,
)
from app.infrastructure.repositories.automation_task_execution_repository import (
    AutomationTaskExecutionRepository,
)
from app.infrastructure.repositories.business_event_repository import (
    BusinessEventRepository,
)


class AutomationService:
    def __init__(
        self,
        request_builder: AutomationRequestBuilder,
        workflow_planner: WorkflowPlanner,
        task_orchestrator: TaskOrchestrator,
        execution_monitor: ExecutionMonitor,
        registry: TaskRegistry | None = None,
        session_factory: type[Generator[Session]] | None = None,
    ) -> None:
        self._request_builder = request_builder
        self._workflow_planner = workflow_planner
        self._task_orchestrator = task_orchestrator
        self._execution_monitor = execution_monitor
        self._registry = registry
        self._session_factory = session_factory
        self._last_request: AutomationRequest | None = None
        self._last_execution_plan: ExecutionPlan | None = None
        self._last_execution_id: UUID | None = None

    def execute(
        self,
        decision: BusinessDecision,
        plan: BusinessActionPlan,
        context: BusinessContext,
        execution_id: UUID | None = None,
    ) -> UUID:
        execution_id = execution_id or uuid4()

        if self._session_factory is not None:
            session = next(self._session_factory())
            try:
                repo = AutomationExecutionRepository(session)
                existing = repo.get(execution_id)
                if existing is not None and existing.status in (
                    "completed",
                    "failed",
                    "cancelled",
                ):
                    return execution_id
            finally:
                session.close()

        request = self._request_builder.build(
            decision,
            plan,
            context,
            request_id=execution_id,
        )
        execution_plan = self._workflow_planner.plan(request)

        self._last_request = request
        self._last_execution_plan = execution_plan
        self._last_execution_id = execution_id

        if self._session_factory is not None and self._registry is not None:
            thread = threading.Thread(
                target=self._run_production,
                args=(execution_plan, execution_id),
                daemon=True,
            )
            thread.start()
        else:
            thread = threading.Thread(
                target=self._run_async,
                args=(execution_plan, execution_id),
                daemon=True,
            )
            thread.start()

        return execution_id

    def _run_async(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> None:
        asyncio.run(
            self._task_orchestrator.execute(plan, execution_id),
        )

    def _run_production(
        self,
        plan: ExecutionPlan,
        execution_id: UUID,
    ) -> None:
        session = next(self._session_factory())  # type: ignore[misc]
        try:
            exec_repo = AutomationExecutionRepository(session)
            task_repo = AutomationTaskExecutionRepository(session)
            event_repo = BusinessEventRepository(session)
            ae_publisher = AutomationEventPublisher(
                event_repository=event_repo,
            )
            monitor = PersistentExecutionMonitor(
                execution_repo=exec_repo,
                task_execution_repo=task_repo,
                event_publisher=ae_publisher,
            )
            orch = SequentialTaskOrchestrator(
                registry=self._registry,  # type: ignore[arg-type]
                execution_monitor=monitor,
            )
            asyncio.run(orch.execute(plan, execution_id))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def recover(self) -> int:
        if self._session_factory is None:
            return 0
        session = next(self._session_factory())
        try:
            repo = AutomationExecutionRepository(session)
            running = repo.list_by_status("running")
            count = 0
            for model in running:
                model.status = "failed"
                model.error = "Recovered: execution was in RUNNING state at startup"
                model.finished_at = datetime.now(UTC)
                repo.update(model)
                count += 1
            session.commit()
            return count
        finally:
            session.close()

    def get_metrics(
        self,
    ) -> AutomationMetrics:
        if self._session_factory is None:
            return AutomationMetrics()
        session = next(self._session_factory())
        try:
            repo = AutomationExecutionRepository(session)
            return AutomationMetrics(
                total_executions=repo.count_all(),
                completed=repo.count_by_status("completed"),
                failed=repo.count_by_status("failed"),
                cancelled=repo.count_by_status("cancelled"),
                retries=repo.sum_retries(),
            )
        finally:
            session.close()
