from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.base import BaseRepository


class MessageRepository(BaseRepository[MessageModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MessageModel)

    def list(self, **filters: object) -> list[MessageModel]:
        stmt = select(MessageModel)
        for column, value in filters.items():
            if hasattr(MessageModel, column):
                stmt = stmt.where(getattr(MessageModel, column) == value)
        return list(
            self._session.scalars(
                stmt.order_by(MessageModel.created_at, MessageModel.id)
            ).all()
        )
