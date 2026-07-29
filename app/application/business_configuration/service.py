from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.domain.access.contracts import Permission
from app.domain.business_configuration.contracts import (
    BusinessConfiguration,
    BusinessConfigurationCreate,
    BusinessConfigurationUpdate,
    BusinessHours,
    BusinessPolicy,
    BusinessService,
)
from app.domain.user.contracts import User
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import (
    BusinessConfigurationModel,
)
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.business_configuration_repository import (
    BusinessConfigurationRepository,
)
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.security.authorization import AuthorizationError, require_scoped_permission

_SERVICES_ADAPTER = TypeAdapter(list[BusinessService])
_POLICIES_ADAPTER = TypeAdapter(list[BusinessPolicy])


class BusinessConfigurationNotFoundError(ValueError):
    pass


class BusinessConfigurationConflictError(ValueError):
    pass


class BusinessConfigurationForbiddenError(ValueError):
    pass


class BusinessConfigurationBotNotFoundError(ValueError):
    pass


class BusinessConfigurationOrganizationInactiveError(ValueError):
    pass


class BusinessConfigurationService:
    def __init__(
        self,
        repository: BusinessConfigurationRepository,
        bot_repository: BotRepository,
        organization_repository: OrganizationRepository,
        session: Session,
    ) -> None:
        self._repository = repository
        self._bot_repository = bot_repository
        self._organization_repository = organization_repository
        self._session = session

    def create(
        self,
        bot_id: UUID,
        request: BusinessConfigurationCreate,
        actor: User,
    ) -> BusinessConfiguration:
        bot = self._get_visible_bot(bot_id, actor, "business_configuration.create")
        self._require_active_organization(bot.organization_id)
        if self._repository.find_by_bot(bot_id) is not None:
            raise BusinessConfigurationConflictError(
                "business configuration already exists",
            )

        now = datetime.now(UTC)
        model = BusinessConfigurationModel(
            id=uuid4(),
            bot_id=bot_id,
            business_name=request.business_name,
            description=request.description,
            phone=request.phone,
            email=request.email,
            website=request.website,
            address=request.address,
            timezone=request.timezone,
            business_hours=request.business_hours.model_dump(mode="json"),
            services=[service.model_dump(mode="json") for service in request.services],
            payment_methods=request.payment_methods,
            policies=[policy.model_dump(mode="json") for policy in request.policies],
            service_instructions=request.service_instructions,
            handoff_enabled=request.handoff_enabled,
            handoff_message=request.handoff_message,
            handoff_keywords=request.handoff_keywords,
            handoff_outside_business_hours=request.handoff_outside_business_hours,
            status="configured",
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def get(self, bot_id: UUID, actor: User) -> BusinessConfiguration:
        self._get_visible_bot(bot_id, actor, "business_configuration.read")
        model = self._repository.find_by_bot(bot_id)
        if model is None:
            raise BusinessConfigurationNotFoundError(
                "business configuration not found",
            )
        return self._to_domain(model)

    def update(
        self,
        bot_id: UUID,
        request: BusinessConfigurationUpdate,
        actor: User,
    ) -> BusinessConfiguration:
        if request.bot_id is not None:
            raise BusinessConfigurationForbiddenError("bot_id cannot be changed")

        bot = self._get_visible_bot(bot_id, actor, "business_configuration.update")
        self._require_active_organization(bot.organization_id)
        model = self._repository.find_by_bot(bot_id)
        if model is None:
            raise BusinessConfigurationNotFoundError(
                "business configuration not found",
            )

        if request.business_name is not None:
            model.business_name = request.business_name
        if request.description is not None:
            model.description = request.description
        if "phone" in request.model_fields_set:
            model.phone = request.phone
        if "email" in request.model_fields_set:
            model.email = request.email
        if "website" in request.model_fields_set:
            model.website = request.website
        if "address" in request.model_fields_set:
            model.address = request.address
        if request.timezone is not None:
            model.timezone = request.timezone
        if request.business_hours is not None:
            model.business_hours = request.business_hours.model_dump(mode="json")
        if request.services is not None:
            model.services = [
                service.model_dump(mode="json") for service in request.services
            ]
        if request.payment_methods is not None:
            model.payment_methods = request.payment_methods
        if request.policies is not None:
            model.policies = [
                policy.model_dump(mode="json") for policy in request.policies
            ]
        if request.service_instructions is not None:
            model.service_instructions = request.service_instructions
        if request.handoff_enabled is not None:
            model.handoff_enabled = request.handoff_enabled
        if "handoff_message" in request.model_fields_set:
            model.handoff_message = request.handoff_message
        if request.handoff_keywords is not None:
            model.handoff_keywords = request.handoff_keywords
        if request.handoff_outside_business_hours is not None:
            model.handoff_outside_business_hours = (
                request.handoff_outside_business_hours
            )

        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def _get_visible_bot(
        self,
        bot_id: UUID,
        actor: User,
        permission: Permission,
    ) -> BotModel:
        bot = self._bot_repository.get(bot_id)
        if bot is None:
            raise BusinessConfigurationBotNotFoundError("bot not found")
        try:
            require_scoped_permission(actor, permission, bot.organization_id)
        except AuthorizationError as exc:
            raise BusinessConfigurationForbiddenError("permission denied") from exc
        return bot

    def _require_active_organization(self, organization_id: UUID) -> None:
        organization = self._organization_repository.get(organization_id)
        if organization is None or organization.status != "active":
            raise BusinessConfigurationOrganizationInactiveError(
                "organization is inactive",
            )

    @staticmethod
    def _to_domain(model: BusinessConfigurationModel) -> BusinessConfiguration:
        return BusinessConfiguration(
            id=model.id,
            bot_id=model.bot_id,
            business_name=model.business_name,
            description=model.description,
            phone=model.phone,
            email=model.email,
            website=model.website,
            address=model.address,
            timezone=model.timezone,
            business_hours=BusinessHours.model_validate(model.business_hours),
            services=_SERVICES_ADAPTER.validate_python(model.services),
            payment_methods=model.payment_methods,
            policies=_POLICIES_ADAPTER.validate_python(model.policies),
            service_instructions=model.service_instructions,
            handoff_enabled=model.handoff_enabled,
            handoff_message=model.handoff_message,
            handoff_keywords=model.handoff_keywords,
            handoff_outside_business_hours=model.handoff_outside_business_hours,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
