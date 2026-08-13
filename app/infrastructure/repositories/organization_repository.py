from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[OrganizationModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OrganizationModel)

    def find_by_slug(self, slug: str) -> OrganizationModel | None:
        stmt = select(OrganizationModel).where(OrganizationModel.slug == slug)
        return self._session.scalars(stmt).first()

    def get_for_update(self, organization_id: UUID) -> OrganizationModel | None:
        stmt = (
            select(OrganizationModel)
            .where(OrganizationModel.id == organization_id)
            .with_for_update()
        )
        return self._session.scalars(stmt).first()

    def list_ordered(self) -> list[OrganizationModel]:
        stmt = select(OrganizationModel).order_by(OrganizationModel.created_at)
        return list(self._session.scalars(stmt).all())

    def exists_with_slug(self, slug: str, exclude_id: UUID | None = None) -> bool:
        model = self.find_by_slug(slug)
        if model is None:
            return False
        return exclude_id is None or model.id != exclude_id
