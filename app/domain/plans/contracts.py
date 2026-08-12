from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PlanStatus = Literal["active", "retired"]
PlanFeatureKey = Literal[
    "analytics",
    "analytics_export",
    "audit",
    "integrations",
    "automations",
    "human_handoff",
    "business_calendar",
    "knowledge",
    "whatsapp_configuration",
]
PlanLimitKey = Literal[
    "max_active_bots",
    "max_active_users",
    "max_integrations",
    "max_automations",
    "max_business_calendars",
    "max_whatsapp_configurations",
    "max_knowledge_entries",
]
PlanActionClass = Literal[
    "consuming_action", "reducing_action", "read_action", "runtime_action"
]


class PlanFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analytics: bool
    analytics_export: bool
    audit: bool
    integrations: bool
    automations: bool
    human_handoff: bool
    business_calendar: bool
    knowledge: bool
    whatsapp_configuration: bool


class LimitedLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["limited"]
    value: Annotated[int, Field(ge=0)]


class UnlimitedLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unlimited"]


PlanLimit = Annotated[LimitedLimit | UnlimitedLimit, Field(discriminator="kind")]


class PlanLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_active_bots: PlanLimit
    max_active_users: PlanLimit
    max_integrations: PlanLimit
    max_automations: PlanLimit
    max_business_calendars: PlanLimit
    max_whatsapp_configurations: PlanLimit
    max_knowledge_entries: PlanLimit


class PlanConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    features: PlanFeatures
    limits: PlanLimits


class PlanDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    plan_code: str
    display_name: str
    status: PlanStatus
    configuration: PlanConfiguration
    created_at: datetime
    updated_at: datetime


class PlanAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    plan_definition_id: UUID
    version: int
    assigned_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PlanAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_code: Annotated[str, Field(min_length=1, max_length=100)]
    expected_version: Annotated[int, Field(gt=0)]


class EffectivePlanIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    display_name: str


class EffectiveLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["limited", "unlimited"]
    value: int | None = None
    current: int
    reached: bool
    over_limit: bool


class EffectiveLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_active_bots: EffectiveLimit
    max_active_users: EffectiveLimit
    max_integrations: EffectiveLimit
    max_automations: EffectiveLimit
    max_business_calendars: EffectiveLimit
    max_whatsapp_configurations: EffectiveLimit
    max_knowledge_entries: EffectiveLimit


class OrganizationPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: EffectivePlanIdentity
    version: int
    features: PlanFeatures
    limits: EffectiveLimits
