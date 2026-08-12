from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_non_user_audit, append_user_audit
from app.application.plans.service import PlanEnforcementService
from app.domain.access.contracts import Permission
from app.domain.audit.ports import AuditWriter
from app.domain.human_handoff.contracts import HandoffSessionResponse
from app.domain.user.contracts import User
from app.infrastructure.models.analytics import HandoffCycleModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import (
    HandoffEventModel,
    HandoffSessionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.security.authorization import (
    AuthorizationError,
    is_platform_admin,
    require_scoped_permission,
)


class HandoffError(ValueError):
    pass


class HandoffForbiddenError(HandoffError):
    pass


class HandoffConflictError(HandoffError):
    pass


class HandoffNotFoundError(HandoffError):
    pass


class HumanHandoffService:
    def __init__(
        self,
        repository: HumanHandoffRepository,
        session: Session,
        audit_writer: AuditWriter,
        plan_enforcement: PlanEnforcementService,
    ) -> None:
        self._repository, self._session = repository, session
        self._audit_writer = audit_writer
        self._plan_enforcement = plan_enforcement

    def request(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        actor: User,
        reason_code: str | None,
    ) -> HandoffSessionResponse:
        self._authorize(actor, "handoff.request", organization_id)
        self._plan_enforcement.require_consuming_action(
            organization_id, feature="human_handoff"
        )
        conversation = self._conversation(conversation_id, organization_id)
        existing = self._repository.get(conversation_id, organization_id, lock=True)
        if existing and existing.status in {"waiting_human", "human_active"}:
            raise HandoffConflictError("handoff is already active")
        now = datetime.now(UTC)
        if existing is None:
            existing = HandoffSessionModel(
                id=uuid4(),
                conversation_id=conversation.id,
                organization_id=organization_id,
                bot_id=conversation.bot_id,
                status="waiting_human",
                requested_at=now,
                reason_code=reason_code,
                last_activity_at=now,
            )
            self._repository.add(
                existing,
                HandoffEventModel(
                    handoff_session_id=existing.id,
                    organization_id=organization_id,
                    actor_user_id=actor.id,
                    event_type="requested",
                    reason_code=reason_code,
                ),
            )
        else:
            (
                existing.status,
                existing.assigned_user_id,
                existing.requested_at,
                existing.reason_code,
            ) = ("waiting_human", None, now, reason_code)
            self._repository.event(existing, "requested", actor.id, reason_code)
        self._repository.add_cycle(
            HandoffCycleModel(
                organization_id=organization_id,
                conversation_id=conversation.id,
                bot_id=conversation.bot_id,
                handoff_session_id=existing.id,
                requested_at=now,
            )
        )
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="handoff.requested",
            resource_type="handoff",
            resource_id=existing.id,
            occurred_at=now,
        )
        self._commit()
        return _response(existing)

    def request_automation(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        reason_code: str,
    ) -> HandoffSessionResponse:
        """Internal, deliberately narrow entrypoint used by durable automation.

        It can only request a handoff and deliberately records no impersonated user.
        """
        if reason_code not in {"outside_business_hours", "automation_rule"}:
            raise HandoffForbiddenError("automation reason is not allowed")
        conversation = self._conversation(conversation_id, organization_id)
        existing = self._repository.get(conversation_id, organization_id, lock=True)
        if existing and existing.status in {"waiting_human", "human_active"}:
            raise HandoffConflictError("handoff is already active")
        now = datetime.now(UTC)
        if existing is None:
            existing = HandoffSessionModel(
                id=uuid4(),
                conversation_id=conversation.id,
                organization_id=organization_id,
                bot_id=conversation.bot_id,
                status="waiting_human",
                requested_at=now,
                reason_code=reason_code,
                last_activity_at=now,
            )
            self._repository.add(
                existing,
                HandoffEventModel(
                    handoff_session_id=existing.id,
                    organization_id=organization_id,
                    actor_user_id=None,
                    event_type="requested",
                    reason_code=reason_code,
                ),
            )
        else:
            existing.status, existing.assigned_user_id = "waiting_human", None
            existing.requested_at, existing.reason_code = now, reason_code
            self._repository.event(existing, "requested", None, reason_code)
        self._repository.add_cycle(
            HandoffCycleModel(
                organization_id=organization_id,
                conversation_id=conversation.id,
                bot_id=conversation.bot_id,
                handoff_session_id=existing.id,
                requested_at=now,
            )
        )
        append_non_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor_type="automation",
            action="handoff.requested",
            resource_type="handoff",
            resource_id=existing.id,
            occurred_at=now,
        )
        self._commit()
        return _response(existing)

    def claim(
        self, organization_id: UUID, conversation_id: UUID, actor: User
    ) -> HandoffSessionResponse:
        self._authorize(actor, "handoff.claim", organization_id)
        row = self._active(conversation_id, organization_id)
        if row.assigned_user_id not in {None, actor.id}:
            raise HandoffConflictError("handoff is assigned to another user")
        self._active_user(actor.id, organization_id)
        row.assigned_user_id, row.assigned_at, row.status, row.version = (
            actor.id,
            datetime.now(UTC),
            "human_active",
            row.version + 1,
        )
        self._repository.event(row, "claimed", actor.id)
        self._activate_cycle(row, row.assigned_at)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="handoff.claimed",
            resource_type="handoff",
            resource_id=row.id,
            occurred_at=row.assigned_at,
        )
        self._commit()
        return _response(row)

    def release(
        self, organization_id: UUID, conversation_id: UUID, actor: User
    ) -> HandoffSessionResponse:
        self._authorize(actor, "handoff.release", organization_id)
        row = self._active(conversation_id, organization_id)
        self._assigned_or_privileged(row, actor)
        row.assigned_user_id, row.assigned_at, row.status, row.version = (
            None,
            None,
            "waiting_human",
            row.version + 1,
        )
        self._repository.event(row, "released", actor.id)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="handoff.released",
            resource_type="handoff",
            resource_id=row.id,
        )
        self._commit()
        return _response(row)

    def transfer(
        self, organization_id: UUID, conversation_id: UUID, actor: User, user_id: UUID
    ) -> HandoffSessionResponse:
        self._authorize(actor, "handoff.transfer", organization_id)
        row = self._active(conversation_id, organization_id)
        self._assigned_or_privileged(row, actor)
        self._active_user(user_id, organization_id)
        row.assigned_user_id, row.assigned_at, row.status, row.version = (
            user_id,
            datetime.now(UTC),
            "human_active",
            row.version + 1,
        )
        self._repository.event(row, "transferred", actor.id)
        self._activate_cycle(row, row.assigned_at)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="handoff.transferred",
            resource_type="handoff",
            resource_id=row.id,
            occurred_at=row.assigned_at,
        )
        self._commit()
        return _response(row)

    def resolve(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        actor: User,
        *,
        return_to_bot: bool,
    ) -> HandoffSessionResponse:
        self._authorize(actor, "handoff.resolve", organization_id)
        row = self._active(conversation_id, organization_id)
        self._assigned_or_privileged(row, actor)
        now = datetime.now(UTC)
        (
            row.status,
            row.assigned_user_id,
            row.resolved_at,
            row.last_activity_at,
            row.version,
        ) = (
            ("bot_active" if return_to_bot else "resolved"),
            None,
            now,
            now,
            row.version + 1,
        )
        self._repository.event(
            row, "returned_to_bot" if return_to_bot else "resolved", actor.id
        )
        cycle = self._repository.active_cycle(row.id, organization_id, lock=True)
        if cycle is None:
            raise HandoffConflictError("active handoff cycle not found")
        cycle.resolved_at = now
        cycle.resolution_type = "returned_to_bot" if return_to_bot else "resolved"
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action=("handoff.returned_to_bot" if return_to_bot else "handoff.resolved"),
            resource_type="handoff",
            resource_id=row.id,
            occurred_at=now,
        )
        self._commit()
        return _response(row)

    def get(
        self, organization_id: UUID, conversation_id: UUID, actor: User
    ) -> HandoffSessionResponse:
        self._authorize(actor, "handoff.read", organization_id)
        row = self._repository.get(conversation_id, organization_id)
        if row is None:
            raise HandoffNotFoundError("handoff not found")
        return _response(row)

    def list(
        self,
        organization_id: UUID,
        actor: User,
        *,
        status: str | None,
        bot_id: UUID | None,
        assigned_user_id: UUID | None,
        unassigned_only: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[HandoffSessionResponse], int]:
        self._authorize(actor, "handoff.read", organization_id)
        rows, total = self._repository.list(
            organization_id,
            status=status,
            bot_id=bot_id,
            assigned_user_id=assigned_user_id,
            unassigned_only=unassigned_only,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [_response(row) for row in rows], total

    def blocks_bot(self, organization_id: UUID, conversation_id: UUID) -> bool:
        row = self._repository.get(conversation_id, organization_id)
        return row is not None and row.status in {"waiting_human", "human_active"}

    def authorize_reply(
        self, organization_id: UUID, conversation_id: UUID, actor: User
    ) -> None:
        self._authorize(actor, "handoff.reply", organization_id)
        row = self._active(conversation_id, organization_id)
        if row.status != "human_active":
            raise HandoffConflictError("handoff is not assigned")
        self._assigned_or_privileged(row, actor)
        if row.assigned_user_id is not None:
            self._active_user(row.assigned_user_id, organization_id)

    def _active(
        self, conversation_id: UUID, organization_id: UUID
    ) -> HandoffSessionModel:
        row = self._repository.get(conversation_id, organization_id, lock=True)
        if row is None:
            raise HandoffNotFoundError("handoff not found")
        if row.status not in {"waiting_human", "human_active"}:
            raise HandoffConflictError("handoff is not active")
        return row

    def _conversation(
        self, conversation_id: UUID, organization_id: UUID
    ) -> ConversationModel:
        row = self._session.get(ConversationModel, conversation_id)
        if row is None or row.organization_id != organization_id or row.bot_id is None:
            raise HandoffNotFoundError("conversation not found")
        return row

    def _active_user(self, user_id: UUID, organization_id: UUID) -> None:
        user = self._session.get(UserModel, user_id)
        if (
            user is None
            or user.organization_id != organization_id
            or user.status != "active"
        ):
            raise HandoffConflictError("assigned user is not active")

    def _assigned_or_privileged(self, row: HandoffSessionModel, actor: User) -> None:
        if (
            row.assigned_user_id != actor.id
            and actor.role not in {"organization_owner", "organization_admin"}
            and not is_platform_admin(actor)
        ):
            raise HandoffForbiddenError("handoff is assigned to another user")

    def _authorize(
        self, actor: User, permission: Permission, organization_id: UUID
    ) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise HandoffForbiddenError("permission denied") from exc

    def _activate_cycle(
        self, row: HandoffSessionModel, activated_at: datetime | None
    ) -> None:
        if activated_at is None:
            return
        cycle = self._repository.active_cycle(row.id, row.organization_id, lock=True)
        if cycle is None:
            raise HandoffConflictError("active handoff cycle not found")
        if cycle.activated_at is None:
            cycle.activated_at = activated_at

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise HandoffConflictError("handoff conflict") from exc


def _response(row: HandoffSessionModel) -> HandoffSessionResponse:
    return HandoffSessionResponse(
        id=row.id,
        conversation_id=row.conversation_id,
        organization_id=row.organization_id,
        bot_id=row.bot_id,
        status=row.status,
        assigned_user_id=row.assigned_user_id,
        requested_at=row.requested_at,
        assigned_at=row.assigned_at,
        resolved_at=row.resolved_at,
        reason_code=row.reason_code,
        last_activity_at=row.last_activity_at,
        version=row.version,
    )
