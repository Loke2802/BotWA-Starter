from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.plans.metrics import PlanMetricsRegistry, plan_metrics
from app.domain.audit.contracts import PlanAssignmentMetadata
from app.domain.audit.ports import AuditWriter
from app.domain.plans.contracts import (
    EffectiveLimit,
    EffectiveLimits,
    EffectivePlanIdentity,
    OrganizationPlanResponse,
    PlanDefinition,
    PlanFeatureKey,
    PlanLimit,
    PlanLimitKey,
)
from app.domain.plans.errors import (
    PlanAssignmentNotFound,
    PlanFeatureNotAvailable,
    PlanForbidden,
    PlanLimitReached,
    PlanNotFound,
    PlanUnavailable,
    PlanVersionConflict,
)
from app.domain.user.contracts import User
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.security.authorization import AuthorizationError, require_scoped_permission

LIMIT_KEYS: tuple[PlanLimitKey, ...] = (
    "max_active_bots",
    "max_active_users",
    "max_integrations",
    "max_automations",
    "max_business_calendars",
    "max_whatsapp_configurations",
    "max_knowledge_entries",
)


class PlanEnforcementService:
    def __init__(
        self,
        repository: SqlAlchemyPlanRepository,
        *,
        metrics: PlanMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.metrics = metrics or plan_metrics

    def lock_organization(self, organization_id: UUID) -> None:
        if not self.repository.lock_organization(organization_id):
            raise PlanUnavailable("organization is unavailable")

    def require_feature(self, organization_id: UUID, feature: PlanFeatureKey) -> None:
        plan = self._effective_plan(organization_id)
        enabled = getattr(plan.configuration.features, feature)
        self.metrics.record(
            "plan_enforcement_checks_total",
            operation="feature",
            result="allowed" if enabled else "denied",
        )
        if not enabled:
            self.metrics.record(
                "plan_enforcement_denials_total",
                operation="feature",
                result="denied",
            )
            raise PlanFeatureNotAvailable(feature)

    def require_capacity(self, organization_id: UUID, key: PlanLimitKey) -> int:
        plan = self._effective_plan(organization_id)
        limit: PlanLimit = getattr(plan.configuration.limits, key)
        current = self.repository.resource_count(organization_id, key)
        allowed = limit.kind == "unlimited" or current < limit.value
        self.metrics.record(
            "plan_enforcement_checks_total",
            operation="capacity",
            result="allowed" if allowed else "denied",
        )
        if not allowed:
            self.metrics.record(
                "plan_enforcement_denials_total",
                operation="capacity",
                result="denied",
            )
            raise PlanLimitReached(key)
        return current

    def require_consuming_action(
        self,
        organization_id: UUID,
        *,
        feature: PlanFeatureKey | None = None,
        limit: PlanLimitKey | None = None,
    ) -> None:
        self.lock_organization(organization_id)
        if feature is not None:
            self.require_feature(organization_id, feature)
        if limit is not None:
            self.require_capacity(organization_id, limit)

    def _effective_plan(self, organization_id: UUID) -> PlanDefinition:
        assignment = self.repository.get_assignment(organization_id)
        if assignment is None:
            raise PlanAssignmentNotFound("plan assignment not found")
        plan = self.repository.get_plan_by_id(assignment.plan_definition_id)
        if plan is None:
            raise PlanUnavailable("assigned plan is unavailable")
        return plan


class PlanQueryService:
    def __init__(
        self,
        repository: SqlAlchemyPlanRepository,
        enforcement: PlanEnforcementService,
        *,
        metrics: PlanMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.enforcement = enforcement
        self.metrics = metrics or plan_metrics

    def get(self, organization_id: UUID, actor: User) -> OrganizationPlanResponse:
        try:
            require_scoped_permission(actor, "plan.read", organization_id)
        except AuthorizationError as exc:
            raise PlanForbidden("plan access denied") from exc
        assignment = self.repository.get_assignment(organization_id)
        if assignment is None:
            raise PlanAssignmentNotFound("plan assignment not found")
        plan = self.repository.get_plan_by_id(assignment.plan_definition_id)
        if plan is None:
            raise PlanUnavailable("assigned plan is unavailable")
        limits = {
            key: self._effective_limit(
                getattr(plan.configuration.limits, key),
                self.repository.resource_count(organization_id, key),
            )
            for key in LIMIT_KEYS
        }
        self.metrics.record(
            "plan_query_requests_total", operation="query", result="success"
        )
        return OrganizationPlanResponse(
            plan=EffectivePlanIdentity(
                code=plan.plan_code, display_name=plan.display_name
            ),
            version=assignment.version,
            features=plan.configuration.features,
            limits=EffectiveLimits.model_validate(limits),
        )

    @staticmethod
    def _effective_limit(limit: PlanLimit, current: int) -> EffectiveLimit:
        if limit.kind == "unlimited":
            return EffectiveLimit(
                kind="unlimited", current=current, reached=False, over_limit=False
            )
        return EffectiveLimit(
            kind="limited",
            value=limit.value,
            current=current,
            reached=current >= limit.value,
            over_limit=current > limit.value,
        )


class PlanAssignmentService:
    def __init__(
        self,
        repository: SqlAlchemyPlanRepository,
        session: Session,
        audit_writer: AuditWriter,
        query_service: PlanQueryService,
        *,
        metrics: PlanMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.session = session
        self.audit_writer = audit_writer
        self.query_service = query_service
        self.metrics = metrics or plan_metrics

    def assign(
        self,
        organization_id: UUID,
        plan_code: str,
        expected_version: int,
        actor: User,
    ) -> OrganizationPlanResponse:
        try:
            require_scoped_permission(actor, "plan.assign", organization_id)
        except AuthorizationError as exc:
            raise PlanForbidden("plan assignment denied") from exc
        if actor.role != "platform_admin":
            raise PlanForbidden("plan assignment denied")
        if not self.repository.lock_organization(organization_id):
            raise PlanNotFound("organization not found")
        row = self.repository.assignment_model(organization_id)
        if row is None:
            raise PlanAssignmentNotFound("plan assignment not found")
        if row.version != expected_version:
            raise PlanVersionConflict("plan assignment version conflict")
        target = self.repository.get_plan_by_code(plan_code)
        if target is None:
            raise PlanNotFound("plan not found")
        if target.status != "active":
            raise PlanUnavailable("plan is retired")
        current = self.repository.get_plan_by_id(row.plan_definition_id)
        if current is None:
            raise PlanUnavailable("assigned plan is unavailable")
        if current.id == target.id:
            return self.query_service.get(organization_id, actor)
        now = datetime.now(UTC)
        row.plan_definition_id = target.id
        row.version += 1
        row.assigned_by_user_id = actor.id
        row.updated_at = now
        try:
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="plan.changed",
                resource_type="plan_assignment",
                resource_id=None,
                metadata=PlanAssignmentMetadata(
                    from_plan_code=current.plan_code,
                    to_plan_code=target.plan_code,
                ),
                occurred_at=now,
            )
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise PlanUnavailable("plan assignment persistence failed") from exc
        except Exception:
            self.session.rollback()
            raise
        self.metrics.record(
            "plan_assignment_changes_total", operation="assign", result="success"
        )
        return self.query_service.get(organization_id, actor)
