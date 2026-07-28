from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.bot import BotModel
from app.infrastructure.repositories.base import BaseRepository


class BotRepository(BaseRepository[BotModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, BotModel)

    def find_by_organization_and_slug(
        self,
        organization_id: UUID,
        slug: str,
    ) -> BotModel | None:
        stmt = select(BotModel).where(
            BotModel.organization_id == organization_id,
            BotModel.slug == slug,
        )
        return self._session.scalars(stmt).first()

    def list_ordered(self) -> list[BotModel]:
        stmt = select(BotModel).order_by(BotModel.created_at)
        return list(self._session.scalars(stmt).all())

    def list_by_organization(self, organization_id: UUID) -> list[BotModel]:
        stmt = (
            select(BotModel)
            .where(BotModel.organization_id == organization_id)
            .order_by(BotModel.created_at)
        )
        return list(self._session.scalars(stmt).all())
