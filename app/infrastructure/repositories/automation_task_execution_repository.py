from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.automation_task_execution import (
    AutomationTaskExecutionModel,
)
from app.infrastructure.repositories.base import BaseRepository


class AutomationTaskExecutionRepository(
    BaseRepository[AutomationTaskExecutionModel],
):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AutomationTaskExecutionModel)

    def list_by_execution(
        self,
        execution_id: UUID,
    ) -> list[AutomationTaskExecutionModel]:
        stmt = (
            select(AutomationTaskExecutionModel)
            .where(
                AutomationTaskExecutionModel.execution_id == execution_id,
            )
            .order_by(AutomationTaskExecutionModel.order)
        )
        return list(self._session.scalars(stmt).all())
