from uuid import UUID, uuid4

from app.infrastructure.models.automation_execution import (
    AutomationExecutionModel,
)
from app.infrastructure.models.automation_task_execution import (
    AutomationTaskExecutionModel,
)


def test_execution_model_can_be_created() -> None:
    execution_id = uuid4()
    model = AutomationExecutionModel(
        execution_id=execution_id,
        plan_id=uuid4(),
        status="pending",
        error_count=0,
        total_tasks=5,
        completed_tasks=3,
        failed_tasks=1,
    )
    assert model.execution_id == execution_id
    assert model.status == "pending"
    assert model.error_count == 0
    assert model.total_tasks == 5
    assert model.completed_tasks == 3
    assert model.failed_tasks == 1


def test_execution_model_with_full_data() -> None:
    execution_id = uuid4()
    model = AutomationExecutionModel(
        execution_id=execution_id,
        plan_id=uuid4(),
        status="completed",
        error_count=2,
        total_tasks=5,
        completed_tasks=3,
        failed_tasks=2,
        error="Some tasks failed",
    )
    assert model.execution_id == execution_id
    assert model.status == "completed"
    assert model.error_count == 2
    assert model.total_tasks == 5
    assert model.completed_tasks == 3
    assert model.failed_tasks == 2
    assert model.error == "Some tasks failed"


def test_task_execution_model_can_be_created() -> None:
    execution_id = uuid4()
    task_id = uuid4()
    model = AutomationTaskExecutionModel(
        id=uuid4(),
        execution_id=execution_id,
        task_id=task_id,
        action="respond",
        status="pending",
        attempt=0,
    )
    assert isinstance(model.id, UUID)
    assert model.execution_id == execution_id
    assert model.task_id == task_id
    assert model.action == "respond"
    assert model.status == "pending"
    assert model.attempt == 0


def test_task_execution_model_with_full_data() -> None:
    model = AutomationTaskExecutionModel(
        id=uuid4(),
        execution_id=uuid4(),
        task_id=uuid4(),
        action="http_call",
        order=1,
        status="failed",
        attempt=3,
        error="Connection timeout",
    )
    assert model.action == "http_call"
    assert model.order == 1
    assert model.status == "failed"
    assert model.attempt == 3
    assert model.error == "Connection timeout"
