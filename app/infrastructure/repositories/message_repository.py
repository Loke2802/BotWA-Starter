from sqlalchemy.orm import Session

from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.base import BaseRepository


class MessageRepository(BaseRepository[MessageModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MessageModel)
