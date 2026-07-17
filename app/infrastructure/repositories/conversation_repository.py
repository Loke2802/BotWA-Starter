from sqlalchemy.orm import Session

from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[ConversationModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ConversationModel)
