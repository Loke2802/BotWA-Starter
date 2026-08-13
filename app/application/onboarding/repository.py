from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.plans.contracts import PlanConfiguration
from app.infrastructure.models.onboarding import OrganizationOnboardingModel


@dataclass(frozen=True)
class OrganizationSnapshot:
    id: UUID
    name: str
    slug: str
    status: str
    settings: dict[str, object]
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None


@dataclass(frozen=True)
class PlanSnapshot:
    assignment_exists: bool
    plan_exists: bool
    plan_status: str | None
    configuration: PlanConfiguration | None


@dataclass(frozen=True)
class BotSnapshot:
    id: UUID
    status: str
    business_configuration_id: UUID | None
    business_configuration_status: str | None
    business_configuration_valid: bool
    any_bot_exists: bool


@dataclass(frozen=True)
class WhatsAppSnapshot:
    id: UUID
    status: str
    webhook_enabled: bool
    verify_token_configured: bool
    access_token_configured: bool
    app_secret_configured: bool


@dataclass(frozen=True)
class KnowledgeSnapshot:
    published_entry_id: UUID | None


@dataclass(frozen=True)
class IntegrationSnapshot:
    id: UUID | None
    status: str | None
    has_credentials: bool
    health_status: str | None
    health_checked: bool
    any_connection_exists: bool


class OnboardingRepository(Protocol):
    def get(self, organization_id: UUID) -> OrganizationOnboardingModel | None: ...

    def get_for_update(
        self, organization_id: UUID
    ) -> OrganizationOnboardingModel | None: ...

    def add(self, workflow: OrganizationOnboardingModel) -> None: ...

    def lock_organization(self, organization_id: UUID) -> bool: ...

    def organization(self, organization_id: UUID) -> OrganizationSnapshot | None: ...

    def has_active_owner(self, organization_id: UUID) -> bool: ...

    def plan(self, organization_id: UUID) -> PlanSnapshot: ...

    def initial_bot(self, organization_id: UUID) -> BotSnapshot | None: ...

    def whatsapp(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> WhatsAppSnapshot | None: ...

    def knowledge(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> KnowledgeSnapshot: ...

    def integration(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> IntegrationSnapshot: ...
