from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.automation_execution import (
    AutomationExecutionModel,
)
from app.infrastructure.repositories.base import BaseRepository


class AutomationExecutionRepository(BaseRepository[AutomationExecutionModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AutomationExecutionModel)

    def list_by_status(self, status: str) -> list[AutomationExecutionModel]:
        stmt = (
            select(AutomationExecutionModel)
            .where(AutomationExecutionModel.status == status)
            .order_by(AutomationExecutionModel.created_at)
        )
        return list(self._session.scalars(stmt).all())

    def count_by_status(self, status: str) -> int:
        stmt = select(AutomationExecutionModel).where(
            AutomationExecutionModel.status == status
        )
        return len(list(self._session.scalars(stmt).all()))

    def count_all(self) -> int:
        stmt = select(AutomationExecutionModel)
        return len(list(self._session.scalars(stmt).all()))

    def sum_retries(self) -> int:
        stmt = select(AutomationExecutionModel)
        return sum(m.error_count or 0 for m in self._session.scalars(stmt).all())
