from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.domain.organization.contracts import (
    Organization,
    OrganizationCreate,
    OrganizationSettings,
    OrganizationUpdate,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)


class OrganizationNotFoundError(ValueError):
    pass


class OrganizationConflictError(ValueError):
    pass


class OrganizationService:
    def __init__(
        self,
        repository: OrganizationRepository,
        session: Session,
    ) -> None:
        self._repository = repository
        self._session = session

    def create(self, request: OrganizationCreate) -> Organization:
        if self._repository.find_by_slug(request.slug) is not None:
            raise OrganizationConflictError("organization slug already exists")

        now = datetime.now(UTC)
        model = OrganizationModel(
            id=uuid4(),
            name=request.name,
            slug=request.slug,
            status="active",
            settings=request.settings.model_dump(),
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def get(self, organization_id: UUID) -> Organization:
        model = self._repository.get(organization_id)
        if model is None:
            raise OrganizationNotFoundError("organization not found")
        return self._to_domain(model)

    def list(self) -> list[Organization]:
        return [self._to_domain(model) for model in self._repository.list_ordered()]

    def update(
        self,
        organization_id: UUID,
        request: OrganizationUpdate,
    ) -> Organization:
        model = self._repository.get(organization_id)
        if model is None:
            raise OrganizationNotFoundError("organization not found")

        if request.slug is not None and request.slug != model.slug:
            existing = self._repository.find_by_slug(request.slug)
            if existing is not None and existing.id != organization_id:
                raise OrganizationConflictError("organization slug already exists")
            model.slug = request.slug

        if request.name is not None:
            model.name = request.name
        if request.settings is not None:
            model.settings = request.settings.model_dump()

        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def deactivate(self, organization_id: UUID) -> Organization:
        model = self._repository.get(organization_id)
        if model is None:
            raise OrganizationNotFoundError("organization not found")

        if model.status != "inactive":
            now = datetime.now(UTC)
            model.status = "inactive"
            model.deactivated_at = now
            model.updated_at = now
            self._repository.update(model)
            self._session.commit()
            self._session.refresh(model)
        return self._to_domain(model)

    @staticmethod
    def _to_domain(model: OrganizationModel) -> Organization:
        settings_data = model.settings or {}
        return Organization(
            id=model.id,
            name=model.name,
            slug=model.slug,
            status=model.status,
            settings=OrganizationSettings.model_validate(settings_data),
            created_at=model.created_at,
            updated_at=model.updated_at,
            deactivated_at=model.deactivated_at,
        )
