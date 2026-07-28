from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.business.contracts import (
    BusinessActionPlan,
    BusinessContext,
    BusinessDecision,
)


class AutomationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: UUID
    decision: BusinessDecision
    action_plan: BusinessActionPlan
    context: BusinessContext
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_attempts: int = 3
    delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0


class Task(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: UUID
    action: str
    target: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)
    order: int = 0
    dependencies: list[UUID] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_seconds: float = 30.0


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: UUID
    request_id: UUID
    tasks: list[Task] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class ExecutionStatusType(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: UUID
    status: TaskExecutionStatus = TaskExecutionStatus.PENDING
    attempt: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result_data: dict[str, object] = Field(default_factory=dict)


class ExecutionStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    plan_id: UUID
    status: ExecutionStatusType = ExecutionStatusType.PENDING
    tasks: dict[UUID, TaskExecution] = Field(default_factory=dict)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    error_count: int = 0


class AutomationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: UUID
    status: ExecutionStatusType
    completed_tasks: list[UUID] = Field(default_factory=list)
    failed_tasks: list[UUID] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    result_data: dict[str, object] = Field(default_factory=dict)
    finished_at: datetime
