from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.models.analytics import HandoffCycleModel
from app.infrastructure.models.human_handoff import (
    HandoffEventModel,
    HandoffSessionModel,
)


class HumanHandoffRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(
        self, conversation_id: UUID, organization_id: UUID, *, lock: bool = False
    ) -> HandoffSessionModel | None:
        stmt = select(HandoffSessionModel).where(
            HandoffSessionModel.conversation_id == conversation_id,
            HandoffSessionModel.organization_id == organization_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).one_or_none()

    def add(self, row: HandoffSessionModel, event: HandoffEventModel) -> None:
        self._session.add(row)
        self._session.flush()
        self._session.add(event)
        self._session.flush()

    def event(
        self,
        row: HandoffSessionModel,
        event_type: str,
        actor_id: UUID | None,
        reason_code: str | None = None,
    ) -> None:
        self._session.add(
            HandoffEventModel(
                handoff_session_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=actor_id,
                event_type=event_type,
                reason_code=reason_code,
            )
        )

    def add_cycle(self, cycle: HandoffCycleModel) -> None:
        self._session.add(cycle)
        self._session.flush()

    def active_cycle(
        self, handoff_session_id: UUID, organization_id: UUID, *, lock: bool = False
    ) -> HandoffCycleModel | None:
        stmt = select(HandoffCycleModel).where(
            HandoffCycleModel.handoff_session_id == handoff_session_id,
            HandoffCycleModel.organization_id == organization_id,
            HandoffCycleModel.resolved_at.is_(None),
        )
        if lock:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).one_or_none()

    def list(
        self,
        organization_id: UUID,
        *,
        status: str | None,
        bot_id: UUID | None,
        assigned_user_id: UUID | None,
        unassigned_only: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[HandoffSessionModel], int]:
        filters = [HandoffSessionModel.organization_id == organization_id]
        if status is not None:
            filters.append(HandoffSessionModel.status == status)
        if bot_id is not None:
            filters.append(HandoffSessionModel.bot_id == bot_id)
        if assigned_user_id is not None:
            filters.append(HandoffSessionModel.assigned_user_id == assigned_user_id)
        if unassigned_only:
            filters.append(HandoffSessionModel.assigned_user_id.is_(None))
        stmt = (
            select(HandoffSessionModel)
            .where(*filters)
            .order_by(
                HandoffSessionModel.last_activity_at.desc(), HandoffSessionModel.id
            )
            .offset(offset)
            .limit(limit)
        )
        total = select(func.count()).select_from(HandoffSessionModel).where(*filters)
        return list(self._session.scalars(stmt).all()), int(
            self._session.execute(total).scalar_one()
        )
