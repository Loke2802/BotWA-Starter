from sqlalchemy.orm import Session

from app.infrastructure.models.knowledge_source import KnowledgeSourceModel
from app.infrastructure.repositories.base import BaseRepository


class KnowledgeSourceRepository(BaseRepository[KnowledgeSourceModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeSourceModel)
