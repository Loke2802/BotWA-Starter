from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.integration_event import IntegrationEventModel


class IntegrationEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: IntegrationEventModel) -> None:
        self._session.add(event)

    def get(self, event_id: UUID) -> IntegrationEventModel | None:
        return self._session.get(IntegrationEventModel, event_id)

    def list(
        self,
        provider_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IntegrationEventModel]:
        stmt = select(IntegrationEventModel).order_by(
            IntegrationEventModel.created_at.desc()
        )
        if provider_id is not None:
            stmt = stmt.where(IntegrationEventModel.provider_id == provider_id)
        if event_type is not None:
            stmt = stmt.where(IntegrationEventModel.event_type == event_type)
        stmt = stmt.offset(offset).limit(limit)
        return list(self._session.scalars(stmt).all())

    def count_by_provider(self, provider_id: str) -> int:
        stmt = select(IntegrationEventModel).where(
            IntegrationEventModel.provider_id == provider_id
        )
        return len(list(self._session.scalars(stmt).all()))
