from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TriggerType = Literal["conversation.inbound_received"]
ActionType = Literal["request_handoff"]
BusinessHoursState = Literal["inside", "outside", "unknown"]
ReasonCode = Literal["outside_business_hours", "automation_rule"]


class AutomationConditions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel_type: str | None = Field(default=None, max_length=50)
    bot_id: str | None = None
    business_hours_state: BusinessHoursState | None = None
    conversation_status: Literal["open", "closed", "archived"] | None = None
    handoff_active: bool | None = None


class RequestHandoffAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason_code: ReasonCode = "automation_rule"


class AutomationDefinitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    bot_id: str | None = None
    trigger_type: TriggerType
    conditions_data: AutomationConditions = Field(default_factory=AutomationConditions)
    action_type: ActionType
    action_data: RequestHandoffAction = Field(default_factory=RequestHandoffAction)

    @model_validator(mode="after")
    def allowed_pair(self) -> "AutomationDefinitionInput":
        if (
            self.trigger_type != "conversation.inbound_received"
            or self.action_type != "request_handoff"
        ):
            raise ValueError("automation trigger/action combination is not allowed")
        return self


class AutomationDefinitionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    bot_id: UUID | None = None
    conditions_data: AutomationConditions | None = None
    action_data: RequestHandoffAction | None = None


class AutomationDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    id: UUID
    organization_id: UUID
    bot_id: UUID | None
    name: str
    description: str | None
    trigger_type: TriggerType
    conditions_data: AutomationConditions
    action_type: ActionType
    action_data: RequestHandoffAction
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class AutomationDefinitionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[AutomationDefinitionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class AutomationExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
    id: UUID
    organization_id: UUID
    automation_definition_id: UUID
    definition_version: int
    event_receipt_id: UUID
    status: str
    attempt_count: int
    available_at: datetime
    safe_error_code: str | None
    created_at: datetime
    updated_at: datetime


class AutomationExecutionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: list[AutomationExecutionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
