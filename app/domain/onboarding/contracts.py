from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OnboardingWorkflowStatus = Literal["not_started", "in_progress", "completed"]
OnboardingCurrentReadiness = Literal["not_ready", "ready", "degraded"]
StepClassification = Literal["required", "conditional", "optional"]
StepStatus = Literal["ready", "incomplete", "blocked", "not_applicable"]
ExternalValidation = Literal["not_required", "pending", "unknown", "last_known_valid"]
OnboardingStepCode = Literal[
    "organization_profile",
    "owner_ready",
    "initial_bot",
    "business_configuration",
    "whatsapp",
    "knowledge",
    "integrations",
    "review",
]
ActionHint = Literal[
    "configure_organization",
    "manage_users",
    "create_bot",
    "activate_bot",
    "configure_business",
    "configure_whatsapp",
    "manage_knowledge",
    "manage_integrations",
    "complete_onboarding",
]
BlockingReason = Literal[
    "ORGANIZATION_INACTIVE",
    "OWNER_REQUIRED",
    "PLAN_ASSIGNMENT_REQUIRED",
    "PLAN_UNAVAILABLE",
    "BOT_REQUIRED",
    "BOT_INACTIVE",
    "BUSINESS_CONFIGURATION_REQUIRED",
    "WHATSAPP_CONFIGURATION_REQUIRED",
    "PLAN_FEATURE_UNAVAILABLE",
    "KNOWLEDGE_NOT_PUBLISHED",
    "INTEGRATION_INACTIVE",
]
ResourceType = Literal[
    "organization",
    "bot",
    "business_configuration",
    "whatsapp_configuration",
    "knowledge",
    "integration",
]


class ResourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_type: ResourceType
    resource_id: UUID


class OnboardingStepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: OnboardingStepCode
    classification: StepClassification
    applicable: bool
    status: StepStatus
    blocking_reason_code: BlockingReason | None = None
    resource_reference: ResourceReference | None = None
    action_hint: ActionHint | None = None
    setup_ready: bool | None = None
    external_validation: ExternalValidation = "not_required"


class OnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    workflow_status: OnboardingWorkflowStatus
    version: int | None
    started_at: datetime | None
    completed_at: datetime | None
    current_readiness: OnboardingCurrentReadiness
    ready_to_complete: bool
    next_step: OnboardingStepCode | None
    steps: tuple[OnboardingStepResponse, ...]
    calculated_at: datetime


class OnboardingCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: Annotated[int, Field(gt=0)]
