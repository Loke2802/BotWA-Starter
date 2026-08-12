from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.knowledge_management.provider import knowledge_entry_from_model
from app.application.knowledge_management.repository import KnowledgeEntryRepository
from app.application.plans.service import PlanEnforcementService
from app.domain.access.contracts import Permission
from app.domain.knowledge_management.contracts import (
    KnowledgeEntry,
    KnowledgeEntryCreate,
    KnowledgeEntryStatus,
    KnowledgeEntryUpdate,
)
from app.domain.user.contracts import User
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.security.authorization import AuthorizationError, require_scoped_permission


class KnowledgeEntryNotFoundError(ValueError):
    pass


class KnowledgeEntryForbiddenError(ValueError):
    pass


class KnowledgeEntryConflictError(ValueError):
    pass


class KnowledgeEntryBotNotFoundError(ValueError):
    pass


class KnowledgeEntryOrganizationInactiveError(ValueError):
    pass


class KnowledgeManagementService:
    def __init__(
        self,
        repository: KnowledgeEntryRepository,
        bot_repository: BotRepository,
        organization_repository: OrganizationRepository,
        session: Session,
        plan_enforcement: PlanEnforcementService,
    ) -> None:
        self._repository = repository
        self._bot_repository = bot_repository
        self._organization_repository = organization_repository
        self._session = session
        self._plan_enforcement = plan_enforcement

    def create(
        self,
        organization_id: UUID,
        bot_id: UUID,
        request: KnowledgeEntryCreate,
        actor: User,
    ) -> KnowledgeEntry:
        self._validate_scope(organization_id, bot_id, actor, "knowledge.create")
        self._require_active_organization(organization_id)
        self._plan_enforcement.require_consuming_action(
            organization_id,
            feature="knowledge",
            limit="max_knowledge_entries",
        )
        now = datetime.now(UTC)
        model = KnowledgeEntryModel(
            id=uuid4(),
            organization_id=organization_id,
            bot_id=bot_id,
            title=request.title,
            content=request.content,
            status="draft",
            source_type="manual",
            metadata_data=request.metadata,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        self._commit()
        self._session.refresh(model)
        return knowledge_entry_from_model(model)

    def list(
        self,
        organization_id: UUID,
        bot_id: UUID,
        actor: User,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KnowledgeEntry], int]:
        self._validate_scope(organization_id, bot_id, actor, "knowledge.read")
        offset = (page - 1) * page_size
        models = self._repository.list_scoped(
            organization_id,
            bot_id,
            status=status,
            search=search,
            offset=offset,
            limit=page_size,
        )
        total = self._repository.count_scoped(
            organization_id,
            bot_id,
            status=status,
            search=search,
        )
        return [knowledge_entry_from_model(model) for model in models], total

    def get(
        self,
        organization_id: UUID,
        bot_id: UUID,
        entry_id: UUID,
        actor: User,
    ) -> KnowledgeEntry:
        self._validate_scope(organization_id, bot_id, actor, "knowledge.read")
        return knowledge_entry_from_model(
            self._get_entry(entry_id, organization_id, bot_id),
        )

    def update(
        self,
        organization_id: UUID,
        bot_id: UUID,
        entry_id: UUID,
        request: KnowledgeEntryUpdate,
        actor: User,
    ) -> KnowledgeEntry:
        self._validate_scope(organization_id, bot_id, actor, "knowledge.update")
        self._require_active_organization(organization_id)
        model = self._get_entry(entry_id, organization_id, bot_id)
        if model.status == "archived":
            raise KnowledgeEntryConflictError("archived entries cannot be updated")
        if request.title is not None:
            model.title = request.title
        if request.content is not None:
            model.content = request.content
        if request.metadata is not None:
            model.metadata_data = request.metadata
        model.updated_by_user_id = actor.id
        model.updated_at = datetime.now(UTC)
        self._commit()
        self._session.refresh(model)
        return knowledge_entry_from_model(model)

    def publish(
        self,
        organization_id: UUID,
        bot_id: UUID,
        entry_id: UUID,
        actor: User,
    ) -> KnowledgeEntry:
        return self._transition(
            organization_id,
            bot_id,
            entry_id,
            actor,
            permission="knowledge.publish",
            expected={"draft"},
            target="published",
        )

    def archive(
        self,
        organization_id: UUID,
        bot_id: UUID,
        entry_id: UUID,
        actor: User,
    ) -> KnowledgeEntry:
        return self._transition(
            organization_id,
            bot_id,
            entry_id,
            actor,
            permission="knowledge.delete",
            expected={"draft", "published"},
            target="archived",
        )

    def delete(
        self,
        organization_id: UUID,
        bot_id: UUID,
        entry_id: UUID,
        actor: User,
    ) -> None:
        self._validate_scope(organization_id, bot_id, actor, "knowledge.delete")
        self._require_active_organization(organization_id)
        model = self._get_entry(entry_id, organization_id, bot_id)
        self._repository.delete(model)
        self._commit()

    def _transition(
        self,
        organization_id: UUID,
        bot_id: UUID,
        entry_id: UUID,
        actor: User,
        *,
        permission: Permission,
        expected: set[str],
        target: str,
    ) -> KnowledgeEntry:
        self._validate_scope(organization_id, bot_id, actor, permission)
        self._require_active_organization(organization_id)
        if target == "published":
            self._plan_enforcement.require_consuming_action(
                organization_id, feature="knowledge"
            )
        model = self._get_entry(entry_id, organization_id, bot_id)
        if model.status not in expected:
            raise KnowledgeEntryConflictError(
                f"cannot transition knowledge entry from {model.status} to {target}",
            )
        model.status = target
        model.updated_by_user_id = actor.id
        model.updated_at = datetime.now(UTC)
        self._commit()
        self._session.refresh(model)
        return knowledge_entry_from_model(model)

    def _validate_scope(
        self,
        organization_id: UUID,
        bot_id: UUID,
        actor: User,
        permission: Permission,
    ) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise KnowledgeEntryForbiddenError("permission denied") from exc
        bot = self._bot_repository.get(bot_id)
        if bot is None or bot.organization_id != organization_id:
            raise KnowledgeEntryBotNotFoundError("bot not found")

    def _require_active_organization(self, organization_id: UUID) -> None:
        organization = self._organization_repository.get(organization_id)
        if organization is None or organization.status != "active":
            raise KnowledgeEntryOrganizationInactiveError(
                "organization is inactive",
            )

    def _get_entry(
        self,
        entry_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
    ) -> KnowledgeEntryModel:
        model = self._repository.get_scoped(entry_id, organization_id, bot_id)
        if model is None:
            raise KnowledgeEntryNotFoundError("knowledge entry not found")
        return model

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise KnowledgeEntryConflictError("knowledge entry conflict") from exc
