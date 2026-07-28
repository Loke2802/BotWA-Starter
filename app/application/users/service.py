from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.domain.organization.contracts import Organization
from app.domain.user.contracts import User, UserCreate, UserUpdate
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.security.passwords import PasswordService


class UserNotFoundError(ValueError):
    pass


class UserConflictError(ValueError):
    pass


class OrganizationInactiveError(ValueError):
    pass


class UserAuthenticationRequiredError(ValueError):
    pass


class UserForbiddenError(ValueError):
    pass


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        organization_repository: OrganizationRepository,
        password_service: PasswordService,
        session: Session,
    ) -> None:
        self._repository = repository
        self._organization_repository = organization_repository
        self._password_service = password_service
        self._session = session

    def create(self, request: UserCreate, actor: User | None = None) -> User:
        organization = self._organization_repository.get(request.organization_id)
        if organization is None:
            raise UserNotFoundError("organization not found")
        if organization.status != "active":
            raise OrganizationInactiveError("organization is inactive")

        user_count = self._repository.count_by_organization(request.organization_id)
        if user_count > 0:
            if actor is None:
                raise UserAuthenticationRequiredError("authentication required")
            if actor.organization_id != request.organization_id:
                raise UserForbiddenError("user belongs to another organization")

        if self._repository.find_by_email(request.email) is not None:
            raise UserConflictError("user email already exists")

        now = datetime.now(UTC)
        model = UserModel(
            id=uuid4(),
            organization_id=request.organization_id,
            email=request.email,
            password_hash=self._password_service.hash(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            status="active",
            auth_version=1,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def get(self, user_id: UUID, actor: User) -> User:
        model = self._get_visible_model(user_id, actor)
        return self._to_domain(model)

    def list(self, actor: User) -> list[User]:
        models = [
            model
            for model in self._repository.list_ordered()
            if model.organization_id == actor.organization_id
        ]
        return [self._to_domain(model) for model in models]

    def update(self, user_id: UUID, request: UserUpdate, actor: User) -> User:
        if request.organization_id is not None:
            raise UserForbiddenError("organization_id cannot be changed")

        model = self._get_visible_model(user_id, actor)
        if "first_name" in request.model_fields_set:
            model.first_name = request.first_name
        if "last_name" in request.model_fields_set:
            model.last_name = request.last_name
        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def deactivate(self, user_id: UUID, actor: User) -> User:
        model = self._get_visible_model(user_id, actor)
        if model.status != "inactive":
            now = datetime.now(UTC)
            model.status = "inactive"
            model.deactivated_at = now
            model.updated_at = now
            model.auth_version += 1
            self._repository.update(model)
            self._session.commit()
            self._session.refresh(model)
        return self._to_domain(model)

    def get_model(self, user_id: UUID) -> UserModel | None:
        return self._repository.get(user_id)

    def find_by_email(self, email: str) -> UserModel | None:
        return self._repository.find_by_email(email)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self._password_service.verify(password, password_hash)

    def record_login(self, model: UserModel) -> User:
        model.last_login_at = datetime.now(UTC)
        model.updated_at = model.last_login_at
        self._repository.update(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> User:
        model = self._repository.get(user_id)
        if model is None:
            raise UserNotFoundError("user not found")
        if not self._password_service.verify(current_password, model.password_hash):
            raise UserAuthenticationRequiredError("invalid credentials")

        model.password_hash = self._password_service.hash(new_password)
        model.auth_version += 1
        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def _get_visible_model(self, user_id: UUID, actor: User) -> UserModel:
        model = self._repository.get(user_id)
        if model is None:
            raise UserNotFoundError("user not found")
        if model.organization_id != actor.organization_id:
            raise UserForbiddenError("user belongs to another organization")
        return model

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            organization_id=model.organization_id,
            email=model.email,
            first_name=model.first_name,
            last_name=model.last_name,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_login_at=model.last_login_at,
            deactivated_at=model.deactivated_at,
        )

    @staticmethod
    def _organization_to_domain(model: OrganizationModel) -> Organization:
        return Organization(
            id=model.id,
            name=model.name,
            slug=model.slug,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deactivated_at=model.deactivated_at,
        )
