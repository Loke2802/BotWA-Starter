from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
    ManagedAutomationExecutionModel,
)


class ManagedAutomationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def definition(
        self, organization_id: UUID, automation_id: UUID, *, lock: bool = False
    ) -> ManagedAutomationDefinitionModel | None:
        stmt = select(ManagedAutomationDefinitionModel).where(
            ManagedAutomationDefinitionModel.id == automation_id,
            ManagedAutomationDefinitionModel.organization_id == organization_id,
        )
        return self.session.scalars(
            stmt.with_for_update() if lock else stmt
        ).one_or_none()

    def definitions(
        self,
        organization_id: UUID,
        *,
        status: str | None,
        bot_id: UUID | None,
        trigger_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ManagedAutomationDefinitionModel], int]:
        filters = [ManagedAutomationDefinitionModel.organization_id == organization_id]
        for column, value in (
            (ManagedAutomationDefinitionModel.status, status),
            (ManagedAutomationDefinitionModel.bot_id, bot_id),
            (ManagedAutomationDefinitionModel.trigger_type, trigger_type),
        ):
            if value is not None:
                filters.append(column == value)
        stmt = (
            select(ManagedAutomationDefinitionModel)
            .where(*filters)
            .order_by(
                ManagedAutomationDefinitionModel.created_at.desc(),
                ManagedAutomationDefinitionModel.id,
            )
            .offset(offset)
            .limit(limit)
        )
        total = (
            select(func.count())
            .select_from(ManagedAutomationDefinitionModel)
            .where(*filters)
        )
        return list(self.session.scalars(stmt)), int(self.session.scalar(total) or 0)

    def active(
        self, organization_id: UUID, bot_id: UUID
    ) -> list[ManagedAutomationDefinitionModel]:
        return list(
            self.session.scalars(
                select(ManagedAutomationDefinitionModel).where(
                    ManagedAutomationDefinitionModel.organization_id == organization_id,
                    ManagedAutomationDefinitionModel.status == "active",
                    or_(
                        ManagedAutomationDefinitionModel.bot_id.is_(None),
                        ManagedAutomationDefinitionModel.bot_id == bot_id,
                    ),
                )
            )
        )

    def executions(
        self,
        organization_id: UUID,
        automation_id: UUID | None,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ManagedAutomationExecutionModel], int]:
        filters = [ManagedAutomationExecutionModel.organization_id == organization_id]
        if automation_id is not None:
            filters.append(
                ManagedAutomationExecutionModel.automation_definition_id
                == automation_id
            )
        stmt = (
            select(ManagedAutomationExecutionModel)
            .where(*filters)
            .order_by(
                ManagedAutomationExecutionModel.created_at.desc(),
                ManagedAutomationExecutionModel.id,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(stmt)), int(
            self.session.scalar(
                select(func.count())
                .select_from(ManagedAutomationExecutionModel)
                .where(*filters)
            )
            or 0
        )

    def execution(
        self, organization_id: UUID, execution_id: UUID, *, lock: bool = False
    ) -> ManagedAutomationExecutionModel | None:
        stmt = select(ManagedAutomationExecutionModel).where(
            ManagedAutomationExecutionModel.organization_id == organization_id,
            ManagedAutomationExecutionModel.id == execution_id,
        )
        return self.session.scalars(
            stmt.with_for_update() if lock else stmt
        ).one_or_none()

    def claim(
        self, owner: str, batch_size: int, lease_seconds: int
    ) -> list[ManagedAutomationExecutionModel]:
        now = datetime.now(UTC)
        rows = list(
            self.session.scalars(
                select(ManagedAutomationExecutionModel)
                .where(
                    or_(
                        (ManagedAutomationExecutionModel.status == "pending")
                        & (ManagedAutomationExecutionModel.available_at <= now),
                        (ManagedAutomationExecutionModel.status == "running")
                        & (ManagedAutomationExecutionModel.lease_expires_at < now),
                    )
                )
                .order_by(
                    ManagedAutomationExecutionModel.available_at,
                    ManagedAutomationExecutionModel.id,
                )
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )
        from datetime import timedelta

        for row in rows:
            row.status, row.lease_owner, row.lease_expires_at, row.started_at = (
                "running",
                owner,
                now + timedelta(seconds=lease_seconds),
                row.started_at or now,
            )
            row.attempt_count += 1
        self.session.commit()
        return rows
