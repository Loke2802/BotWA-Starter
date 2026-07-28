from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    conversation_id: UUID


class BusinessContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: BusinessRequest
    intent: str = ""
    customer_profile: dict[str, object] = Field(default_factory=dict)
    channel_metadata: dict[str, object] = Field(default_factory=dict)


class BusinessDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    intent: str
    confidence: str
    needs_knowledge: bool = False
    knowledge_content: str | None = None


class BusinessIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    confidence: str = "medium"


class BusinessConstraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    description: str
    applies: bool
    reason: str = ""


class BusinessConstraints(BaseModel):
    model_config = ConfigDict(frozen=True)

    constraints: list[BusinessConstraint] = Field(default_factory=list)
    is_feasible: bool = True


class BusinessOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    score: float = 0.0
    confidence: str = "low"
    rationale: str = ""


class BusinessOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    options: list[BusinessOption] = Field(default_factory=list)
    selected_index: int | None = None


class ActionStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    target: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)
    order: int = 0


class BusinessActionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps: list[ActionStep] = Field(default_factory=list)
    total_steps: int = 0


class BusinessEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str
    source: str
    payload: dict[str, object] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conversation_id: UUID | None = None
