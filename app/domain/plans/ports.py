from typing import Protocol
from uuid import UUID

from app.domain.plans.contracts import (
    PlanAssignment,
    PlanDefinition,
    PlanLimitKey,
)


class PlanCatalogReader(Protocol):
    def get_plan_by_code(self, plan_code: str) -> PlanDefinition | None: ...

    def get_plan_by_id(self, plan_id: UUID) -> PlanDefinition | None: ...


class PlanAssignmentRepository(Protocol):
    def get_assignment(self, organization_id: UUID) -> PlanAssignment | None: ...

    def create_default_assignment(self, organization_id: UUID) -> None: ...

    def resource_count(self, organization_id: UUID, key: PlanLimitKey) -> int: ...

    def lock_organization(self, organization_id: UUID) -> bool: ...
