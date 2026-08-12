from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.plans.service import PlanEnforcementService
from app.domain.access.contracts import Permission
from app.domain.audit.contracts import ChangedFieldsMetadata, StatusTransitionMetadata
from app.domain.audit.ports import AuditWriter
from app.domain.bot.contracts import Bot, BotCreate, BotUpdate
from app.domain.user.contracts import User
from app.infrastructure.models.bot import BotModel
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.security.authorization import (
    AuthorizationError,
    is_platform_admin,
    require_permission,
    require_scoped_permission,
)


class BotNotFoundError(ValueError):
    pass


class BotConflictError(ValueError):
    pass


class BotForbiddenError(ValueError):
    pass


class BotOrganizationNotFoundError(ValueError):
    pass


class BotOrganizationInactiveError(ValueError):
    pass


class BotService:
    def __init__(
        self,
        repository: BotRepository,
        organization_repository: OrganizationRepository,
        session: Session,
        audit_writer: AuditWriter,
        plan_enforcement: PlanEnforcementService,
    ) -> None:
        self._repository = repository
        self._organization_repository = organization_repository
        self._session = session
        self._audit_writer = audit_writer
        self._plan_enforcement = plan_enforcement

    def create(self, request: BotCreate, actor: User) -> Bot:
        organization_id = self._resolve_target_organization(request, actor)
        self._require_active_organization(organization_id)
        self._require_scoped(actor, "bots.create", organization_id)
        self._ensure_slug_available(organization_id, request.slug)

        now = datetime.now(UTC)
        model = BotModel(
            id=uuid4(),
            organization_id=organization_id,
            name=request.name,
            slug=request.slug,
            description=request.description,
            status="inactive",
            default_language=request.default_language,
            timezone=request.timezone,
            welcome_message=request.welcome_message,
            away_message=request.away_message,
            settings=request.settings,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="bot.created",
            resource_type="bot",
            resource_id=model.id,
            occurred_at=now,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def get(self, bot_id: UUID, actor: User) -> Bot:
        model = self._get_visible_model(bot_id, actor, "bots.read")
        return self._to_domain(model)

    def list(self, actor: User) -> list[Bot]:
        try:
            require_permission(actor, "bots.read")
        except AuthorizationError as exc:
            raise BotForbiddenError("permission denied") from exc
        if is_platform_admin(actor):
            models = self._repository.list_ordered()
        else:
            models = self._repository.list_by_organization(actor.organization_id)
        return [self._to_domain(model) for model in models]

    def update(self, bot_id: UUID, request: BotUpdate, actor: User) -> Bot:
        if request.organization_id is not None:
            raise BotForbiddenError("organization_id cannot be changed")

        model = self._get_visible_model(bot_id, actor, "bots.update")
        self._require_active_organization(model.organization_id)
        changed_fields = tuple(
            field
            for field in (
                "name",
                "slug",
                "description",
                "default_language",
                "timezone",
                "welcome_message",
                "away_message",
                "settings",
            )
            if field in request.model_fields_set
        )

        if request.slug is not None and request.slug != model.slug:
            self._ensure_slug_available(model.organization_id, request.slug, model.id)
            model.slug = request.slug
        if request.name is not None:
            model.name = request.name
        if "description" in request.model_fields_set:
            model.description = request.description
        if request.default_language is not None:
            model.default_language = request.default_language
        if request.timezone is not None:
            model.timezone = request.timezone
        if "welcome_message" in request.model_fields_set:
            model.welcome_message = request.welcome_message
        if "away_message" in request.model_fields_set:
            model.away_message = request.away_message
        if request.settings is not None:
            model.settings = request.settings

        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        if changed_fields:
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="bot.updated",
                resource_type="bot",
                resource_id=model.id,
                metadata=ChangedFieldsMetadata(changed_fields=changed_fields),
                occurred_at=model.updated_at,
            )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def activate(self, bot_id: UUID, actor: User) -> Bot:
        model = self._get_visible_model(bot_id, actor, "bots.activate")
        self._require_active_organization(model.organization_id)
        if model.status != "active":
            self._plan_enforcement.require_consuming_action(
                model.organization_id, limit="max_active_bots"
            )
            now = datetime.now(UTC)
            model.status = "active"
            model.activated_at = now
            model.updated_at = now
            self._repository.update(model)
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="bot.activated",
                resource_type="bot",
                resource_id=model.id,
                metadata=StatusTransitionMetadata(
                    from_status="inactive", to_status="active"
                ),
                occurred_at=now,
            )
            self._commit()
            self._session.refresh(model)
        return self._to_domain(model)

    def deactivate(self, bot_id: UUID, actor: User) -> Bot:
        model = self._get_visible_model(bot_id, actor, "bots.deactivate")
        self._require_active_organization(model.organization_id)
        if model.status != "inactive":
            now = datetime.now(UTC)
            model.status = "inactive"
            model.deactivated_at = now
            model.updated_at = now
            self._repository.update(model)
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="bot.deactivated",
                resource_type="bot",
                resource_id=model.id,
                metadata=StatusTransitionMetadata(
                    from_status="active", to_status="inactive"
                ),
                occurred_at=now,
            )
            self._commit()
            self._session.refresh(model)
        return self._to_domain(model)

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise BotConflictError("bot persistence failed") from exc

    def _resolve_target_organization(self, request: BotCreate, actor: User) -> UUID:
        if is_platform_admin(actor):
            if request.organization_id is None:
                raise BotOrganizationNotFoundError("organization not found")
            return request.organization_id
        if (
            request.organization_id is not None
            and request.organization_id != actor.organization_id
        ):
            raise BotForbiddenError("permission denied")
        return actor.organization_id

    def _get_visible_model(
        self,
        bot_id: UUID,
        actor: User,
        permission: Permission,
    ) -> BotModel:
        model = self._repository.get(bot_id)
        if model is None:
            raise BotNotFoundError("bot not found")
        self._require_scoped(actor, permission, model.organization_id)
        return model

    def _require_scoped(
        self,
        actor: User,
        permission: Permission,
        organization_id: UUID,
    ) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise BotForbiddenError("permission denied") from exc

    def _require_active_organization(self, organization_id: UUID) -> None:
        organization = self._organization_repository.get(organization_id)
        if organization is None:
            raise BotOrganizationNotFoundError("organization not found")
        if organization.status != "active":
            raise BotOrganizationInactiveError("organization is inactive")

    def _ensure_slug_available(
        self,
        organization_id: UUID,
        slug: str,
        exclude_id: UUID | None = None,
    ) -> None:
        existing = self._repository.find_by_organization_and_slug(
            organization_id,
            slug,
        )
        if existing is not None and existing.id != exclude_id:
            raise BotConflictError("bot slug already exists")

    @staticmethod
    def _to_domain(model: BotModel) -> Bot:
        return Bot(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            status=model.status,
            default_language=model.default_language,
            timezone=model.timezone,
            welcome_message=model.welcome_message,
            away_message=model.away_message,
            settings=model.settings or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
            activated_at=model.activated_at,
            deactivated_at=model.deactivated_at,
        )
