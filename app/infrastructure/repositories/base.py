from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import Base


class BaseRepository[T: Base]:
    def __init__(self, session: Session, model: type[T]) -> None:
        self._session = session
        self._model = model

    def add(self, entity: T) -> None:
        self._session.add(entity)

    def get(self, id: UUID) -> T | None:
        return self._session.get(self._model, id)

    def list(self, **filters: object) -> list[T]:
        stmt = select(self._model)
        for column, value in filters.items():
            if hasattr(self._model, column):
                stmt = stmt.where(getattr(self._model, column) == value)
        return list(self._session.scalars(stmt).all())

    def update(self, entity: T) -> None:
        self._session.merge(entity)

    def delete(self, id: UUID) -> bool:
        entity = self.get(id)
        if entity is None:
            return False
        self._session.delete(entity)
        return True
