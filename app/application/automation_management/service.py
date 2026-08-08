from builtins import list as builtin_list
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.business_calendar.compatibility import (
    BusinessHoursStateCompatibilityService,
)
from app.application.business_calendar.service import BusinessCalendarService
from app.application.human_handoff.service import HumanHandoffService
from app.domain.automation_management.contracts import (
    AutomationDefinitionInput,
    BusinessHoursState,
)
from app.domain.automation_management.ports import BusinessHoursStateProvider
from app.domain.user.contracts import User
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from app.security.authorization import AuthorizationError, require_scoped_permission
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class AutomationError(ValueError):
    pass


class AutomationNotFoundError(AutomationError):
    pass


class AutomationConflictError(AutomationError):
    pass


class AutomationForbiddenError(AutomationError):
    pass


class AutomationValidationError(AutomationError):
    pass


class AutomationRetryNotAllowedError(AutomationConflictError):
    pass


class ManagedAutomationService:
    def __init__(
        self,
        repository: ManagedAutomationRepository,
        session: Session,
        handoff: HumanHandoffService | None = None,
        business_hours: BusinessHoursStateProvider | None = None,
    ) -> None:
        self.repo, self.session, self.handoff = repository, session, handoff
        self.business_hours = business_hours or BusinessHoursStateCompatibilityService(
            BusinessCalendarService(BusinessCalendarRepository(session), session),
            session,
        )

    def _auth(self, actor: User, permission: str, organization_id: UUID) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)  # type: ignore[arg-type]
        except AuthorizationError as exc:
            raise AutomationForbiddenError("permission denied") from exc

    def create(
        self, organization_id: UUID, payload: AutomationDefinitionInput, actor: User
    ) -> ManagedAutomationDefinitionModel:
        self._auth(actor, "automation.create", organization_id)
        from app.infrastructure.models.managed_automation import (
            ManagedAutomationDefinitionModel,
        )

        now = datetime.now(UTC)
        row = ManagedAutomationDefinitionModel(
            id=uuid4(),
            organization_id=organization_id,
            bot_id=UUID(payload.bot_id) if payload.bot_id else None,
            name=payload.name,
            description=payload.description,
            trigger_type=payload.trigger_type,
            conditions_data=payload.conditions_data.model_dump(mode="json"),
            action_type=payload.action_type,
            action_data=payload.action_data.model_dump(mode="json"),
            status="draft",
            version=1,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def get(
        self, organization_id: UUID, automation_id: UUID, actor: User
    ) -> ManagedAutomationDefinitionModel:
        self._auth(actor, "automation.read", organization_id)
        row = self.repo.definition(organization_id, automation_id)
        if row is None:
            raise AutomationNotFoundError("automation not found")
        return row

    def list(
        self,
        organization_id: UUID,
        actor: User,
        *,
        status: str | None,
        bot_id: UUID | None,
        trigger_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ManagedAutomationDefinitionModel], int]:
        self._auth(actor, "automation.read", organization_id)
        return self.repo.definitions(
            organization_id,
            status=status,
            bot_id=bot_id,
            trigger_type=trigger_type,
            offset=offset,
            limit=limit,
        )

    def list_executions(
        self,
        organization_id: UUID,
        automation_id: UUID,
        actor: User,
        *,
        offset: int,
        limit: int,
    ) -> tuple[builtin_list[ManagedAutomationExecutionModel], int]:
        self._auth(actor, "automation.executions.read", organization_id)
        if self.repo.definition(organization_id, automation_id) is None:
            raise AutomationNotFoundError("automation not found")
        return self.repo.executions(
            organization_id, automation_id, offset=offset, limit=limit
        )

    def get_execution(
        self, organization_id: UUID, execution_id: UUID, actor: User
    ) -> ManagedAutomationExecutionModel:
        self._auth(actor, "automation.executions.read", organization_id)
        row = self.repo.execution(organization_id, execution_id)
        if row is None:
            raise AutomationNotFoundError("automation execution not found")
        return row

    def retry_execution(
        self, organization_id: UUID, execution_id: UUID, actor: User
    ) -> ManagedAutomationExecutionModel:
        self._auth(actor, "automation.executions.retry", organization_id)
        row = self.repo.execution(organization_id, execution_id, lock=True)
        if row is None:
            raise AutomationNotFoundError("automation execution not found")
        if row.status != "failed" or row.attempt_count >= 3:
            raise AutomationRetryNotAllowedError("execution cannot be retried")
        row.status, row.available_at, row.safe_error_code = (
            "pending",
            datetime.now(UTC),
            None,
        )
        self.session.commit()
        return row

    def update(
        self,
        organization_id: UUID,
        automation_id: UUID,
        data: dict[str, object],
        actor: User,
    ) -> ManagedAutomationDefinitionModel:
        self._auth(actor, "automation.update", organization_id)
        row = self.repo.definition(organization_id, automation_id, lock=True)
        if row is None:
            raise AutomationNotFoundError("automation not found")
        if row.status == "active" and any(
            k in data
            for k in {
                "bot_id",
                "trigger_type",
                "conditions_data",
                "action_type",
                "action_data",
            }
        ):
            raise AutomationConflictError(
                "active automation functional changes are not allowed"
            )
        if row.status == "archived":
            raise AutomationConflictError("archived automation is terminal")
        functional = False
        for key, value in data.items():
            if value is not None and hasattr(row, key):
                setattr(
                    row,
                    key,
                    (
                        value.model_dump(mode="json")
                        if hasattr(value, "model_dump")
                        else value
                    ),
                )
                functional |= key in {
                    "bot_id",
                    "trigger_type",
                    "conditions_data",
                    "action_type",
                    "action_data",
                }
        if functional:
            row.version += 1
        row.updated_by_user_id, row.updated_at = actor.id, datetime.now(UTC)
        self.session.commit()
        return row

    def transition(
        self, organization_id: UUID, automation_id: UUID, target: str, actor: User
    ) -> ManagedAutomationDefinitionModel:
        self._auth(actor, f"automation.{target}", organization_id)
        row = self.repo.definition(organization_id, automation_id, lock=True)
        if row is None:
            raise AutomationNotFoundError("automation not found")
        state = {"activate": "active", "deactivate": "inactive", "archive": "archived"}[
            target
        ]
        allowed = {
            "active": {"draft", "inactive"},
            "inactive": {"active"},
            "archived": {"draft", "active", "inactive"},
        }
        if row.status not in allowed[state]:
            raise AutomationConflictError("invalid automation lifecycle transition")
        row.status, row.updated_by_user_id, row.updated_at = (
            state,
            actor.id,
            datetime.now(UTC),
        )
        if state in {"inactive", "archived"}:
            self.session.query(ManagedAutomationExecutionModel).filter(
                ManagedAutomationExecutionModel.automation_definition_id == row.id,
                ManagedAutomationExecutionModel.status == "pending",
            ).update(
                {"status": "cancelled", "completed_at": datetime.now(UTC)},
                synchronize_session=False,
            )
        self.session.commit()
        return row

    def record_inbound(
        self,
        *,
        organization_id: UUID,
        bot_id: UUID,
        conversation_id: UUID,
        contact_id: UUID | None,
        channel_type: str,
        received_at: datetime,
        business_hours_state: BusinessHoursState,
        source_receipt_id: UUID,
        source_type: str = "inbound",
        source_automation_id: UUID | None = None,
    ) -> None:
        if source_automation_id is not None:
            return
        conversation = self.session.get(ConversationModel, conversation_id)
        if (
            conversation is None
            or conversation.organization_id != organization_id
            or conversation.bot_id != bot_id
        ):
            raise AutomationValidationError("conversation context is invalid")
        handoff_active = (
            self.session.query(HandoffSessionModel)
            .filter(
                HandoffSessionModel.organization_id == organization_id,
                HandoffSessionModel.conversation_id == conversation_id,
                HandoffSessionModel.status.in_(("waiting_human", "human_active")),
            )
            .first()
            is not None
        )
        safe = {
            "organization_id": str(organization_id),
            "bot_id": str(bot_id),
            "conversation_id": str(conversation_id),
            "contact_id": str(contact_id) if contact_id else None,
            "channel_type": channel_type,
            "received_at": received_at.isoformat(),
            "business_hours_state": business_hours_state,
            "conversation_status": conversation.management_status
            or conversation.status,
            "handoff_active": handoff_active,
            "source_receipt_id": str(source_receipt_id),
        }
        receipt = ManagedAutomationEventReceiptModel(
            id=uuid4(),
            organization_id=organization_id,
            bot_id=bot_id,
            source_type=source_type,
            source_event_id=source_receipt_id,
            event_type="conversation.inbound_received",
            event_data=safe,
            correlation_id=uuid4(),
            occurred_at=received_at,
        )
        try:
            self.session.add(receipt)
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            return
        for definition in self.repo.active(organization_id, bot_id):
            snapshot = {
                "trigger_type": definition.trigger_type,
                "conditions_data": definition.conditions_data,
                "action_type": definition.action_type,
                "action_data": definition.action_data,
                "bot_id": str(definition.bot_id) if definition.bot_id else None,
            }
            self.session.add(
                ManagedAutomationExecutionModel(
                    id=uuid4(),
                    organization_id=organization_id,
                    automation_definition_id=definition.id,
                    definition_version=definition.version,
                    event_receipt_id=receipt.id,
                    definition_snapshot=snapshot,
                    event_snapshot=safe,
                    status="pending",
                    attempt_count=0,
                    available_at=datetime.now(UTC),
                    correlation_id=receipt.correlation_id,
                )
            )
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()

    def business_hours_state(
        self,
        organization_id: UUID,
        bot_id: UUID,
        occurred_at: datetime,
    ) -> BusinessHoursState:
        return self.business_hours.state(organization_id, bot_id, occurred_at)

    def run(self, row: ManagedAutomationExecutionModel) -> None:
        definition = row.definition_snapshot
        event = row.event_snapshot
        if not isinstance(definition, dict) or not isinstance(event, dict):
            row.status, row.safe_error_code, row.completed_at = (
                "failed",
                "INVALID_SNAPSHOT",
                datetime.now(UTC),
            )
            row.lease_owner = row.lease_expires_at = None
            self.session.commit()
            return
        conditions = definition.get("conditions_data")
        action = definition.get("action_data")
        conversation_id = event.get("conversation_id")
        if (
            not isinstance(conditions, dict)
            or not isinstance(action, dict)
            or not isinstance(conversation_id, str)
        ):
            row.status, row.safe_error_code, row.completed_at = (
                "failed",
                "INVALID_SNAPSHOT",
                datetime.now(UTC),
            )
            row.lease_owner = row.lease_expires_at = None
            self.session.commit()
            return
        matches = all(event.get(k) == v for k, v in conditions.items() if v is not None)
        if not matches:
            row.status, row.completed_at = "skipped", datetime.now(UTC)
            self.session.commit()
            return
        try:
            if self.handoff is None:
                raise RuntimeError("handoff service unavailable")
            reason = action.get("reason_code", "automation_rule")
            if reason not in {"outside_business_hours", "automation_rule"}:
                raise ValueError("invalid action snapshot")
            self.handoff.request_automation(
                row.organization_id,
                UUID(conversation_id),
                reason,
            )
            row.status, row.completed_at, row.lease_owner, row.lease_expires_at = (
                "succeeded",
                datetime.now(UTC),
                None,
                None,
            )
        except Exception as exc:
            row.lease_owner, row.lease_expires_at, row.safe_error_code = (
                None,
                None,
                (
                    "HANDOFF_CONFLICT"
                    if "already active" in str(exc)
                    else "INTERNAL_ERROR"
                ),
            )
            if row.safe_error_code == "HANDOFF_CONFLICT":
                row.status, row.completed_at = "skipped", datetime.now(UTC)
            elif row.attempt_count >= 3:
                row.status, row.completed_at = "failed", datetime.now(UTC)
            else:
                row.status, row.available_at = "pending", datetime.now(UTC) + timedelta(
                    seconds=(0, 5, 30)[min(row.attempt_count, 2)]
                )
        self.session.commit()
