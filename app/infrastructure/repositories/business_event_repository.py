from sqlalchemy.orm import Session

from app.infrastructure.models.business_event import BusinessEventModel
from app.infrastructure.repositories.base import BaseRepository


class BusinessEventRepository(BaseRepository[BusinessEventModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BusinessEventModel)
