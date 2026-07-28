from sqlalchemy.orm import Session

from app.infrastructure.models.knowledge_query_log import KnowledgeQueryLogModel
from app.infrastructure.repositories.base import BaseRepository


class KnowledgeQueryLogRepository(BaseRepository[KnowledgeQueryLogModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeQueryLogModel)
