from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.business_configuration import (
    BusinessConfigurationModel,
)
from app.infrastructure.repositories.base import BaseRepository


class BusinessConfigurationRepository(BaseRepository[BusinessConfigurationModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BusinessConfigurationModel)

    def find_by_bot(self, bot_id: UUID) -> BusinessConfigurationModel | None:
        stmt = select(BusinessConfigurationModel).where(
            BusinessConfigurationModel.bot_id == bot_id,
        )
        return self._session.scalars(stmt).first()
