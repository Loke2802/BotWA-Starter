from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.application.onboarding.metrics import (
    OnboardingMetricsRegistry,
    onboarding_metrics,
)
from app.application.onboarding.repository import OnboardingRepository
from app.domain.onboarding.contracts import (
    ActionHint,
    BlockingReason,
    ExternalValidation,
    OnboardingResponse,
    OnboardingStepCode,
    OnboardingStepResponse,
    OnboardingWorkflowStatus,
    ResourceReference,
    StepClassification,
    StepStatus,
)
from app.domain.onboarding.errors import (
    OnboardingOrganizationNotFound,
    OnboardingUnavailable,
)
from app.domain.organization.contracts import Organization
from app.infrastructure.models.onboarding import OrganizationOnboardingModel

WORKFLOW_STATUS_ADAPTER: TypeAdapter[OnboardingWorkflowStatus] = TypeAdapter(
    OnboardingWorkflowStatus
)


@dataclass(frozen=True)
class ReadinessResult:
    response: OnboardingResponse
    blocking_reasons: tuple[BlockingReason, ...]
    required_steps_ready: int
    required_steps_total: int


class OnboardingReadinessService:
    def __init__(
        self,
        repository: OnboardingRepository,
        *,
        metrics: OnboardingMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.metrics = metrics or onboarding_metrics

    @staticmethod
    def _step(
        code: OnboardingStepCode,
        classification: StepClassification,
        status: StepStatus,
        *,
        applicable: bool = True,
        reason: BlockingReason | None = None,
        reference: ResourceReference | None = None,
        action: ActionHint | None = None,
        setup_ready: bool | None = None,
        external_validation: ExternalValidation = "not_required",
    ) -> OnboardingStepResponse:
        return OnboardingStepResponse(
            code=code,
            classification=classification,
            applicable=applicable,
            status=status,
            blocking_reason_code=reason,
            resource_reference=reference,
            action_hint=action,
            setup_ready=setup_ready,
            external_validation=external_validation,
        )

    def derive(
        self,
        organization_id: UUID,
        workflow: OrganizationOnboardingModel | None,
    ) -> ReadinessResult:
        try:
            return self._derive(organization_id, workflow)
        except OnboardingOrganizationNotFound:
            self.metrics.record("onboarding_readiness_reads_total", "error")
            raise
        except (SQLAlchemyError, ValidationError, TypeError, ValueError) as exc:
            self.metrics.record("onboarding_readiness_reads_total", "error")
            raise OnboardingUnavailable("onboarding readiness is unavailable") from exc

    def _derive(
        self,
        organization_id: UUID,
        workflow: OrganizationOnboardingModel | None,
    ) -> ReadinessResult:
        calculated_at = datetime.now(UTC)
        organization = self.repository.organization(organization_id)
        if organization is None:
            raise OnboardingOrganizationNotFound("organization not found")
        Organization.model_validate(
            {
                "id": organization.id,
                "name": organization.name,
                "slug": organization.slug,
                "status": organization.status,
                "settings": organization.settings,
                "created_at": organization.created_at,
                "updated_at": organization.updated_at,
                "deactivated_at": organization.deactivated_at,
            }
        )

        blocking: list[BlockingReason] = []
        steps: list[OnboardingStepResponse] = []
        organization_ready = organization.status == "active"
        if not organization_ready:
            blocking.append("ORGANIZATION_INACTIVE")
        steps.append(
            self._step(
                "organization_profile",
                "required",
                "ready" if organization_ready else "blocked",
                reason=None if organization_ready else "ORGANIZATION_INACTIVE",
                reference=ResourceReference(
                    resource_type="organization", resource_id=organization.id
                ),
                action="configure_organization",
            )
        )

        owner_ready = self.repository.has_active_owner(organization_id)
        if not owner_ready:
            blocking.append("OWNER_REQUIRED")
        steps.append(
            self._step(
                "owner_ready",
                "required",
                "ready" if owner_ready else "incomplete",
                reason=None if owner_ready else "OWNER_REQUIRED",
                action="manage_users",
            )
        )

        plan = self.repository.plan(organization_id)
        plan_reason: BlockingReason | None = None
        if not plan.assignment_exists:
            plan_reason = "PLAN_ASSIGNMENT_REQUIRED"
        elif (
            not plan.plan_exists
            or plan.plan_status != "active"
            or plan.configuration is None
        ):
            plan_reason = "PLAN_UNAVAILABLE"
        if plan_reason is not None:
            blocking.append(plan_reason)
        features = None
        if plan_reason is None:
            if plan.configuration is None:
                raise OnboardingUnavailable("plan configuration is unavailable")
            features = plan.configuration.features

        bot = self.repository.initial_bot(organization_id)
        active_bot_id: UUID | None = None
        if bot is None:
            bot_reason: BlockingReason | None = "BOT_REQUIRED"
            bot_action: ActionHint = "create_bot"
            bot_reference = None
        elif bot.status != "active":
            bot_reason = "BOT_INACTIVE"
            bot_action = "activate_bot"
            bot_reference = ResourceReference(resource_type="bot", resource_id=bot.id)
        else:
            bot_reason = None
            bot_action = "activate_bot"
            bot_reference = ResourceReference(resource_type="bot", resource_id=bot.id)
            active_bot_id = bot.id
        if bot_reason is not None:
            blocking.append(bot_reason)
        steps.append(
            self._step(
                "initial_bot",
                "required",
                "ready" if bot_reason is None else "incomplete",
                reason=bot_reason,
                reference=bot_reference,
                action=bot_action,
            )
        )

        business_ready = bool(
            active_bot_id is not None
            and bot is not None
            and bot.business_configuration_id is not None
            and bot.business_configuration_status == "configured"
            and bot.business_configuration_valid
        )
        if not business_ready:
            blocking.append("BUSINESS_CONFIGURATION_REQUIRED")
        business_reference = (
            ResourceReference(
                resource_type="business_configuration",
                resource_id=bot.business_configuration_id,
            )
            if bot is not None and bot.business_configuration_id is not None
            else None
        )
        steps.append(
            self._step(
                "business_configuration",
                "required",
                "ready" if business_ready else "incomplete",
                reason=None if business_ready else "BUSINESS_CONFIGURATION_REQUIRED",
                reference=business_reference,
                action="configure_business",
            )
        )

        whatsapp = self.repository.whatsapp(organization_id, active_bot_id)
        if features is None:
            whatsapp_applicable = True
            whatsapp_ready = False
            whatsapp_status: StepStatus = "blocked"
            whatsapp_reason = plan_reason or "PLAN_UNAVAILABLE"
            whatsapp_external: ExternalValidation = "unknown"
        elif not features.whatsapp_configuration:
            whatsapp_applicable = False
            whatsapp_ready = False
            whatsapp_status = "not_applicable"
            whatsapp_reason = None
            whatsapp_external = "not_required"
        else:
            whatsapp_applicable = True
            whatsapp_ready = bool(
                whatsapp is not None
                and whatsapp.status == "active"
                and whatsapp.webhook_enabled
                and whatsapp.verify_token_configured
                and whatsapp.access_token_configured
                and whatsapp.app_secret_configured
            )
            whatsapp_status = "ready" if whatsapp_ready else "incomplete"
            whatsapp_reason = (
                None if whatsapp_ready else "WHATSAPP_CONFIGURATION_REQUIRED"
            )
            whatsapp_external = "pending" if whatsapp_ready else "unknown"
        if whatsapp_applicable and not whatsapp_ready and plan_reason is None:
            blocking.append("WHATSAPP_CONFIGURATION_REQUIRED")
        whatsapp_reference = (
            ResourceReference(
                resource_type="whatsapp_configuration", resource_id=whatsapp.id
            )
            if whatsapp is not None
            else None
        )
        steps.append(
            self._step(
                "whatsapp",
                "conditional",
                whatsapp_status,
                applicable=whatsapp_applicable,
                reason=whatsapp_reason,
                reference=whatsapp_reference,
                action="configure_whatsapp",
                setup_ready=whatsapp_ready if whatsapp_applicable else None,
                external_validation=whatsapp_external,
            )
        )

        knowledge = self.repository.knowledge(organization_id, active_bot_id)
        if features is None:
            knowledge_applicable = True
            knowledge_status: StepStatus = "blocked"
            knowledge_reason: BlockingReason | None = plan_reason or "PLAN_UNAVAILABLE"
        elif not features.knowledge:
            knowledge_applicable = False
            knowledge_status = "not_applicable"
            knowledge_reason = None
        else:
            knowledge_applicable = True
            knowledge_status = (
                "ready" if knowledge.published_entry_id is not None else "incomplete"
            )
            knowledge_reason = (
                None
                if knowledge.published_entry_id is not None
                else "KNOWLEDGE_NOT_PUBLISHED"
            )
        knowledge_reference = (
            ResourceReference(
                resource_type="knowledge",
                resource_id=knowledge.published_entry_id,
            )
            if knowledge.published_entry_id is not None
            else None
        )
        steps.append(
            self._step(
                "knowledge",
                "optional",
                knowledge_status,
                applicable=knowledge_applicable,
                reason=knowledge_reason,
                reference=knowledge_reference,
                action="manage_knowledge",
            )
        )

        integration = self.repository.integration(organization_id, active_bot_id)
        if features is None:
            integration_applicable = True
            integration_status: StepStatus = "blocked"
            integration_reason: BlockingReason | None = (
                plan_reason or "PLAN_UNAVAILABLE"
            )
            integration_external: ExternalValidation = "unknown"
            integration_setup_ready = False
        elif not features.integrations:
            integration_applicable = False
            integration_status = "not_applicable"
            integration_reason = None
            integration_external = "not_required"
            integration_setup_ready = False
        else:
            integration_applicable = True
            integration_setup_ready = bool(
                integration.id is not None
                and integration.status == "active"
                and integration.has_credentials
            )
            integration_status = "ready" if integration_setup_ready else "incomplete"
            integration_reason = (
                None if integration_setup_ready else "INTEGRATION_INACTIVE"
            )
            if (
                integration_setup_ready
                and integration.health_checked
                and integration.health_status == "healthy"
            ):
                integration_external = "last_known_valid"
            elif integration_setup_ready:
                integration_external = "pending"
            else:
                integration_external = "unknown"
        integration_reference = (
            ResourceReference(resource_type="integration", resource_id=integration.id)
            if integration.id is not None
            else None
        )
        steps.append(
            self._step(
                "integrations",
                "optional",
                integration_status,
                applicable=integration_applicable,
                reason=integration_reason,
                reference=integration_reference,
                action="manage_integrations",
                setup_ready=(
                    integration_setup_ready if integration_applicable else None
                ),
                external_validation=integration_external,
            )
        )

        blocking_reasons = tuple(dict.fromkeys(blocking))
        ready_to_complete = not blocking_reasons
        steps.append(
            self._step(
                "review",
                "required",
                "ready" if ready_to_complete else "blocked",
                reason=blocking_reasons[0] if blocking_reasons else None,
                action="complete_onboarding" if ready_to_complete else None,
            )
        )

        blocking_codes: tuple[OnboardingStepCode, ...] = (
            "organization_profile",
            "owner_ready",
            "initial_bot",
            "business_configuration",
            "whatsapp",
        )
        next_step = next(
            (
                step.code
                for step in steps
                if step.code in blocking_codes
                and step.applicable
                and step.status != "ready"
            ),
            "review",
        )
        workflow_status: OnboardingWorkflowStatus = (
            "not_started"
            if workflow is None
            else WORKFLOW_STATUS_ADAPTER.validate_python(workflow.status)
        )
        if ready_to_complete:
            current_readiness = "ready"
        elif workflow_status == "completed":
            current_readiness = "degraded"
        else:
            current_readiness = "not_ready"
        required_total = 5 + (1 if whatsapp_applicable else 0)
        required_ready = required_total - len(blocking_reasons)
        response = OnboardingResponse(
            organization_id=organization_id,
            workflow_status=workflow_status,
            version=workflow.version if workflow is not None else None,
            started_at=workflow.started_at if workflow is not None else None,
            completed_at=workflow.completed_at if workflow is not None else None,
            current_readiness=current_readiness,
            ready_to_complete=ready_to_complete,
            next_step=next_step,
            steps=tuple(steps),
            calculated_at=calculated_at,
        )
        self.metrics.record("onboarding_readiness_reads_total", current_readiness)
        return ReadinessResult(
            response=response,
            blocking_reasons=blocking_reasons,
            required_steps_ready=max(0, required_ready),
            required_steps_total=required_total,
        )
