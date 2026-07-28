from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserModel]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, UserModel)

    def find_by_email(self, email: str) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.email == email)
        return self._session.scalars(stmt).first()

    def list_ordered(self) -> list[UserModel]:
        stmt = select(UserModel).order_by(UserModel.created_at)
        return list(self._session.scalars(stmt).all())

    def count_by_organization(self, organization_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.organization_id == organization_id)
        )
        return int(self._session.execute(stmt).scalar_one())

    def count_active_owners_by_organization(self, organization_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.organization_id == organization_id,
                UserModel.status == "active",
                UserModel.role == "organization_owner",
            )
        )
        return int(self._session.execute(stmt).scalar_one())
