from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.domain.access.contracts import Role

AuditActorType = Literal["user", "system", "automation"]
AuditResult = Literal["success"]
AuditAction = Literal[
    "organization.created",
    "organization.updated",
    "organization.deactivated",
    "user.created",
    "user.updated",
    "user.deactivated",
    "user.role_changed",
    "user.password_changed",
    "bot.created",
    "bot.updated",
    "bot.activated",
    "bot.deactivated",
    "conversation.closed",
    "conversation.reopened",
    "conversation.archived",
    "handoff.requested",
    "handoff.claimed",
    "handoff.released",
    "handoff.transferred",
    "handoff.resolved",
    "handoff.returned_to_bot",
    "automation.created",
    "automation.updated",
    "automation.activated",
    "automation.deactivated",
    "automation.archived",
    "automation.retry_requested",
    "integration.created",
    "integration.updated",
    "integration.activated",
    "integration.deactivated",
    "integration.archived",
    "integration.credentials_rotated",
    "business_calendar.created",
    "business_calendar.updated",
    "business_calendar.activated",
    "business_calendar.deactivated",
    "business_calendar.archived",
    "plan.assigned",
    "plan.changed",
]
AuditResourceType = Literal[
    "organization",
    "user",
    "bot",
    "conversation",
    "handoff",
    "automation",
    "integration",
    "business_calendar",
    "plan_assignment",
]
AuditStatus = Literal[
    "draft",
    "active",
    "inactive",
    "open",
    "closed",
    "archived",
    "bot_active",
    "waiting_human",
    "human_active",
    "resolved",
    "pending",
    "failed",
]
AuditChangedField = Literal[
    "name",
    "slug",
    "settings",
    "first_name",
    "last_name",
    "description",
    "default_language",
    "timezone",
    "welcome_message",
    "away_message",
    "bot_id",
    "capabilities",
    "configuration",
    "conditions_data",
    "action_data",
    "weekly_schedule",
    "date_exception",
    "holiday",
    "manual_override",
]


class EmptyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChangedFieldsMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    changed_fields: tuple[AuditChangedField, ...] = Field(max_length=20)


class StatusTransitionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_status: AuditStatus
    to_status: AuditStatus


class RoleAssignmentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_role: Role
    to_role: Role


class CredentialRotationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credential_changed: Literal[True] = True


class PlanAssignmentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    from_plan_code: str | None
    to_plan_code: str


AuditMetadata = (
    EmptyMetadata
    | ChangedFieldsMetadata
    | StatusTransitionMetadata
    | RoleAssignmentMetadata
    | CredentialRotationMetadata
    | PlanAssignmentMetadata
)
AUDIT_METADATA_ADAPTER: TypeAdapter[AuditMetadata] = TypeAdapter(AuditMetadata)


class AuditEventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    actor_type: AuditActorType
    actor_user_id: UUID | None = None
    actor_role: Role | None = None
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: UUID | None = None
    result: AuditResult = "success"
    metadata: AuditMetadata = Field(default_factory=EmptyMetadata)
    correlation_id: UUID | None = None
    occurred_at: datetime

    @model_validator(mode="after")
    def actor_shape_is_valid(self) -> "AuditEventDraft":
        if self.actor_type == "user":
            if self.actor_user_id is None or self.actor_role is None:
                raise ValueError("user audit actor requires user id and role")
        elif self.actor_user_id is not None or self.actor_role is not None:
            raise ValueError("non-user audit actor cannot include user fields")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("audit occurred_at must be timezone-aware")
        return self


class AuditActor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: AuditActorType
    user_id: UUID | None
    role: Role | None


class AuditResource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: AuditResourceType
    id: UUID | None


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    occurred_at: datetime
    actor: AuditActor
    action: AuditAction
    resource: AuditResource
    result: AuditResult
    metadata: AuditMetadata
    correlation_id: UUID | None


class AuditEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[AuditEventResponse]
    next_cursor: str | None


class AuditCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurred_at: datetime
    id: UUID


class AuditQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: UUID
    actor_user_id: UUID | None = None
    action: AuditAction | None = None
    resource_type: AuditResourceType | None = None
    resource_id: UUID | None = None
    from_: datetime
    to: datetime
    cursor: AuditCursor | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
