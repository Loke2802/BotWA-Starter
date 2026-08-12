"""Explicit test-only plan collaborators for pre-PRD-018 fixtures.

Production composition must always use ``PlanEnforcementService`` backed by the
same SQLAlchemy session as the business mutation. These collaborators only keep
older unit tests focused on their original domain while still satisfying the
mandatory constructor contract.
"""

from uuid import UUID

from app.application.plans.service import PlanEnforcementService
from app.domain.plans.contracts import PlanFeatureKey, PlanLimitKey
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository


class AllowAllPlanEnforcement(PlanEnforcementService):
    """Test-only explicit entitlement collaborator; never used by production roots."""

    def __init__(self) -> None:
        pass

    def lock_organization(self, organization_id: UUID) -> None:
        pass

    def require_feature(self, organization_id: UUID, feature: PlanFeatureKey) -> None:
        pass

    def require_capacity(self, organization_id: UUID, key: PlanLimitKey) -> int:
        return 0

    def require_consuming_action(
        self,
        organization_id: UUID,
        *,
        feature: PlanFeatureKey | None = None,
        limit: PlanLimitKey | None = None,
    ) -> None:
        pass


class NoOpPlanAssignmentRepository(SqlAlchemyPlanRepository):
    """Test-only bootstrap collaborator for tests outside the plans domain."""

    def __init__(self) -> None:
        pass

    def create_default_assignment(self, organization_id: UUID) -> None:
        pass


def allow_all_plan_enforcement() -> PlanEnforcementService:
    return AllowAllPlanEnforcement()


def no_op_plan_repository() -> SqlAlchemyPlanRepository:
    return NoOpPlanAssignmentRepository()
