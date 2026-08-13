import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.onboarding.metrics import (
    OnboardingMetricsRegistry,
    onboarding_metrics,
)
from app.application.onboarding.readiness import OnboardingReadinessService
from app.application.onboarding.repository import OnboardingRepository
from app.domain.access.contracts import Permission
from app.domain.audit.contracts import OnboardingMetadata
from app.domain.audit.errors import AuditWriteError
from app.domain.audit.ports import AuditWriter
from app.domain.onboarding.contracts import OnboardingResponse
from app.domain.onboarding.errors import (
    OnboardingForbidden,
    OnboardingNotReady,
    OnboardingNotStarted,
    OnboardingOrganizationNotFound,
    OnboardingUnavailable,
    OnboardingVersionConflict,
)
from app.domain.user.contracts import User
from app.infrastructure.models.onboarding import OrganizationOnboardingModel
from app.security.authorization import AuthorizationError, require_scoped_permission

logger = logging.getLogger(__name__)


class OnboardingService:
    def __init__(
        self,
        repository: OnboardingRepository,
        readiness: OnboardingReadinessService,
        session: Session,
        audit_writer: AuditWriter,
        *,
        metrics: OnboardingMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.readiness = readiness
        self.session = session
        self.audit_writer = audit_writer
        self.metrics = metrics or onboarding_metrics

    @staticmethod
    def _authorize(actor: User, permission: Permission, organization_id: UUID) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise OnboardingForbidden("onboarding access denied") from exc

    def get(self, organization_id: UUID, actor: User) -> OnboardingResponse:
        self._authorize(actor, "onboarding.read", organization_id)
        workflow = self.repository.get(organization_id)
        return self.readiness.derive(organization_id, workflow).response

    def start(self, organization_id: UUID, actor: User) -> OnboardingResponse:
        self._authorize(actor, "onboarding.manage", organization_id)
        try:
            if not self.repository.lock_organization(organization_id):
                raise OnboardingOrganizationNotFound("organization not found")
            existing = self.repository.get_for_update(organization_id)
            if existing is not None:
                response = self.readiness.derive(organization_id, existing).response
                # End the read-only transaction before returning so row locks do not
                # survive until request dependency teardown.
                self.session.commit()
                self.metrics.record("onboarding_started_total", "noop")
                return response
            now = datetime.now(UTC)
            workflow = OrganizationOnboardingModel(
                organization_id=organization_id,
                status="in_progress",
                started_at=now,
                started_by_user_id=actor.id,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self.repository.add(workflow)
            self.session.flush()
            readiness = self.readiness.derive(organization_id, workflow)
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="onboarding.started",
                resource_type="onboarding",
                resource_id=organization_id,
                metadata=OnboardingMetadata(
                    workflow_version=workflow.version,
                    required_steps_ready=readiness.required_steps_ready,
                    required_steps_total=readiness.required_steps_total,
                ),
                occurred_at=now,
            )
            self.session.commit()
            self.metrics.record("onboarding_started_total", "created")
            logger.info("onboarding_started", extra={"event": "onboarding_started"})
            return self.readiness.derive(organization_id, workflow).response
        except OnboardingOrganizationNotFound:
            self.session.rollback()
            self.metrics.record("onboarding_started_total", "error")
            raise
        except AuditWriteError as exc:
            self.session.rollback()
            self.metrics.record("onboarding_started_total", "error")
            raise OnboardingUnavailable("onboarding audit is unavailable") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            self.metrics.record("onboarding_started_total", "error")
            raise OnboardingUnavailable("onboarding persistence failed") from exc
        except Exception:
            self.session.rollback()
            raise

    def complete(
        self,
        organization_id: UUID,
        expected_version: int,
        actor: User,
    ) -> OnboardingResponse:
        self._authorize(actor, "onboarding.manage", organization_id)
        try:
            if not self.repository.lock_organization(organization_id):
                raise OnboardingOrganizationNotFound("organization not found")
            workflow = self.repository.get_for_update(organization_id)
            if workflow is None:
                raise OnboardingNotStarted("onboarding has not started")
            if workflow.status == "completed":
                response = self.readiness.derive(organization_id, workflow).response
                # Completed is an idempotent no-op even for a stale expected version;
                # release both locks before the response leaves the service boundary.
                self.session.commit()
                self.metrics.record("onboarding_completion_attempts_total", "noop")
                return response
            if workflow.version != expected_version:
                self.metrics.record("onboarding_completion_attempts_total", "conflict")
                raise OnboardingVersionConflict("onboarding version conflict")
            readiness = self.readiness.derive(organization_id, workflow)
            if not readiness.response.ready_to_complete:
                self.metrics.record("onboarding_completion_attempts_total", "not_ready")
                logger.info(
                    "onboarding_completion_blocked",
                    extra={
                        "event": "onboarding_completion_blocked",
                        "blocking_reasons": readiness.blocking_reasons,
                    },
                )
                raise OnboardingNotReady(readiness.blocking_reasons)
            now = datetime.now(UTC)
            workflow.status = "completed"
            workflow.completed_at = now
            workflow.completed_by_user_id = actor.id
            workflow.version += 1
            workflow.updated_at = now
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="onboarding.completed",
                resource_type="onboarding",
                resource_id=organization_id,
                metadata=OnboardingMetadata(
                    workflow_version=workflow.version,
                    required_steps_ready=readiness.required_steps_ready,
                    required_steps_total=readiness.required_steps_total,
                ),
                occurred_at=now,
            )
            self.session.commit()
            self.metrics.record("onboarding_completion_attempts_total", "completed")
            logger.info("onboarding_completed", extra={"event": "onboarding_completed"})
            return self.readiness.derive(organization_id, workflow).response
        except (
            OnboardingNotStarted,
            OnboardingNotReady,
            OnboardingVersionConflict,
            OnboardingOrganizationNotFound,
        ):
            self.session.rollback()
            raise
        except AuditWriteError as exc:
            self.session.rollback()
            self.metrics.record("onboarding_completion_attempts_total", "error")
            raise OnboardingUnavailable("onboarding audit is unavailable") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            self.metrics.record("onboarding_completion_attempts_total", "error")
            raise OnboardingUnavailable("onboarding persistence failed") from exc
        except Exception:
            self.session.rollback()
            raise
