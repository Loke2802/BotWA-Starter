from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.plans.service import PlanEnforcementService
from app.application.whatsapp_configuration.repository import (
    WhatsAppConfigurationRepository,
)
from app.domain.access.contracts import Permission
from app.domain.audit.contracts import (
    CredentialRotationMetadata,
    StatusTransitionMetadata,
)
from app.domain.audit.ports import AuditWriter
from app.domain.user.contracts import User
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfiguration,
    WhatsAppChannelConfigurationCreate,
    WhatsAppChannelConfigurationStatus,
    WhatsAppChannelConfigurationUpdate,
    WhatsAppSecretRotation,
)
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.bot_repository import BotRepository
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.security.authorization import AuthorizationError, require_scoped_permission
from app.security.secret_cipher import SecretCipher, SecretCipherError


class WhatsAppConfigurationNotFoundError(ValueError):
    pass


class WhatsAppConfigurationForbiddenError(ValueError):
    pass


class WhatsAppConfigurationConflictError(ValueError):
    pass


class WhatsAppConfigurationBotNotFoundError(ValueError):
    pass


class WhatsAppConfigurationOrganizationInactiveError(ValueError):
    pass


class WhatsAppConfigurationService:
    def __init__(
        self,
        repository: WhatsAppConfigurationRepository,
        bot_repository: BotRepository,
        organization_repository: OrganizationRepository,
        secret_cipher: SecretCipher,
        session: Session,
        plan_enforcement: PlanEnforcementService,
        audit_writer: AuditWriter,
    ) -> None:
        self._repository = repository
        self._bot_repository = bot_repository
        self._organization_repository = organization_repository
        self._secret_cipher = secret_cipher
        self._session = session
        self._plan_enforcement = plan_enforcement
        self._audit_writer = audit_writer

    def create(
        self,
        organization_id: UUID,
        bot_id: UUID,
        request: WhatsAppChannelConfigurationCreate,
        actor: User,
    ) -> WhatsAppChannelConfiguration:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.create",
        )
        self._require_active_organization(organization_id)
        if any(
            secret is not None
            for secret in (
                request.verify_token,
                request.access_token,
                request.app_secret,
            )
        ):
            self._require_scoped_permission(
                actor,
                "whatsapp_config.rotate_secrets",
                organization_id,
            )
        self._plan_enforcement.require_consuming_action(
            organization_id,
            feature="whatsapp_configuration",
            limit="max_whatsapp_configurations",
        )
        now = datetime.now(UTC)
        model = WhatsAppChannelConfigurationModel(
            id=uuid4(),
            organization_id=organization_id,
            bot_id=bot_id,
            display_name=request.display_name,
            phone_number_id=request.phone_number_id,
            whatsapp_business_account_id=request.whatsapp_business_account_id,
            public_webhook_id=uuid4(),
            status="draft",
            webhook_enabled=request.webhook_enabled,
            verify_token_ciphertext=self._encrypt_optional(request.verify_token),
            access_token_ciphertext=self._encrypt_optional(request.access_token),
            app_secret_ciphertext=self._encrypt_optional(request.app_secret),
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="whatsapp_configuration.created",
            resource_type="whatsapp_configuration",
            resource_id=model.id,
            occurred_at=now,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def list(
        self,
        organization_id: UUID,
        bot_id: UUID,
        actor: User,
        *,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WhatsAppChannelConfiguration], int]:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.read",
        )
        offset = (page - 1) * page_size
        models = self._repository.list_scoped(
            organization_id,
            bot_id,
            status=status,
            phone_number_id=phone_number_id,
            search=search,
            offset=offset,
            limit=page_size,
        )
        total = self._repository.count_scoped(
            organization_id,
            bot_id,
            status=status,
            phone_number_id=phone_number_id,
            search=search,
        )
        return [self._to_domain(model) for model in models], total

    def get(
        self,
        organization_id: UUID,
        bot_id: UUID,
        configuration_id: UUID,
        actor: User,
    ) -> WhatsAppChannelConfiguration:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.read",
        )
        return self._to_domain(
            self._get_configuration(configuration_id, organization_id, bot_id),
        )

    def update(
        self,
        organization_id: UUID,
        bot_id: UUID,
        configuration_id: UUID,
        request: WhatsAppChannelConfigurationUpdate,
        actor: User,
    ) -> WhatsAppChannelConfiguration:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.update",
        )
        self._require_active_organization(organization_id)
        model = self._get_configuration(
            configuration_id,
            organization_id,
            bot_id,
            for_update=True,
        )
        if request.display_name is not None:
            model.display_name = request.display_name
        if request.phone_number_id is not None:
            model.phone_number_id = request.phone_number_id
        if request.whatsapp_business_account_id is not None:
            model.whatsapp_business_account_id = request.whatsapp_business_account_id
        if request.webhook_enabled is not None:
            model.webhook_enabled = request.webhook_enabled
        if (
            model.status == "active"
            and model.webhook_enabled
            and model.app_secret_ciphertext is None
        ):
            raise WhatsAppConfigurationConflictError(
                "active webhook requires an app secret",
            )
        model.updated_by_user_id = actor.id
        model.updated_at = datetime.now(UTC)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="whatsapp_configuration.updated",
            resource_type="whatsapp_configuration",
            resource_id=model.id,
            occurred_at=model.updated_at,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def activate(
        self,
        organization_id: UUID,
        bot_id: UUID,
        configuration_id: UUID,
        actor: User,
    ) -> WhatsAppChannelConfiguration:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.activate",
        )
        self._require_active_organization(organization_id)
        self._plan_enforcement.require_consuming_action(
            organization_id, feature="whatsapp_configuration"
        )
        model = self._get_configuration(
            configuration_id,
            organization_id,
            bot_id,
            for_update=True,
        )
        if model.status not in {"draft", "inactive"}:
            raise WhatsAppConfigurationConflictError(
                f"cannot activate configuration from {model.status}",
            )
        if model.verify_token_ciphertext is None:
            raise WhatsAppConfigurationConflictError(
                "verify token must be configured before activation",
            )
        if model.webhook_enabled and model.app_secret_ciphertext is None:
            raise WhatsAppConfigurationConflictError(
                "app secret must be configured before webhook activation",
            )
        previous_status = model.status
        model.status = "active"
        model.updated_by_user_id = actor.id
        model.updated_at = datetime.now(UTC)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="whatsapp_configuration.activated",
            resource_type="whatsapp_configuration",
            resource_id=model.id,
            metadata=StatusTransitionMetadata(
                from_status=previous_status, to_status="active"
            ),
            occurred_at=model.updated_at,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def deactivate(
        self,
        organization_id: UUID,
        bot_id: UUID,
        configuration_id: UUID,
        actor: User,
    ) -> WhatsAppChannelConfiguration:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.activate",
        )
        model = self._get_configuration(
            configuration_id,
            organization_id,
            bot_id,
            for_update=True,
        )
        if model.status not in {"draft", "active"}:
            raise WhatsAppConfigurationConflictError(
                f"cannot deactivate configuration from {model.status}",
            )
        previous_status = model.status
        model.status = "inactive"
        model.updated_by_user_id = actor.id
        model.updated_at = datetime.now(UTC)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="whatsapp_configuration.deactivated",
            resource_type="whatsapp_configuration",
            resource_id=model.id,
            metadata=StatusTransitionMetadata(
                from_status=previous_status, to_status="inactive"
            ),
            occurred_at=model.updated_at,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def rotate_secrets(
        self,
        organization_id: UUID,
        bot_id: UUID,
        configuration_id: UUID,
        request: WhatsAppSecretRotation,
        actor: User,
    ) -> WhatsAppChannelConfiguration:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.rotate_secrets",
        )
        self._require_active_organization(organization_id)
        model = self._get_configuration(
            configuration_id,
            organization_id,
            bot_id,
            for_update=True,
        )
        if request.verify_token is not None:
            model.verify_token_ciphertext = self._encrypt(request.verify_token)
        if request.access_token is not None:
            model.access_token_ciphertext = self._encrypt(request.access_token)
        if request.app_secret is not None:
            model.app_secret_ciphertext = self._encrypt(request.app_secret)
        model.updated_by_user_id = actor.id
        model.updated_at = datetime.now(UTC)
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="whatsapp_configuration.credentials_rotated",
            resource_type="whatsapp_configuration",
            resource_id=model.id,
            metadata=CredentialRotationMetadata(),
            occurred_at=model.updated_at,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def delete(
        self,
        organization_id: UUID,
        bot_id: UUID,
        configuration_id: UUID,
        actor: User,
    ) -> None:
        self._validate_scope(
            organization_id,
            bot_id,
            actor,
            "whatsapp_config.delete",
        )
        model = self._get_configuration(
            configuration_id,
            organization_id,
            bot_id,
            for_update=True,
        )
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action="whatsapp_configuration.deleted",
            resource_type="whatsapp_configuration",
            resource_id=model.id,
        )
        self._repository.delete(model)
        self._commit()

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
            raise WhatsAppConfigurationForbiddenError("permission denied") from exc
        bot = self._bot_repository.get(bot_id)
        if bot is None or bot.organization_id != organization_id:
            raise WhatsAppConfigurationBotNotFoundError("bot not found")

    def _require_active_organization(self, organization_id: UUID) -> None:
        organization = self._organization_repository.get(organization_id)
        if organization is None or organization.status != "active":
            raise WhatsAppConfigurationOrganizationInactiveError(
                "organization is inactive",
            )

    @staticmethod
    def _require_scoped_permission(
        actor: User,
        permission: Permission,
        organization_id: UUID,
    ) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise WhatsAppConfigurationForbiddenError("permission denied") from exc

    def _get_configuration(
        self,
        configuration_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
        *,
        for_update: bool = False,
    ) -> WhatsAppChannelConfigurationModel:
        model = self._repository.get_scoped(
            configuration_id,
            organization_id,
            bot_id,
            for_update=for_update,
        )
        if model is None:
            raise WhatsAppConfigurationNotFoundError(
                "WhatsApp configuration not found",
            )
        return model

    def _encrypt_optional(self, value: str | None) -> str | None:
        return None if value is None else self._encrypt(value)

    def _encrypt(self, value: str) -> str:
        try:
            return self._secret_cipher.encrypt(value)
        except SecretCipherError as exc:
            raise WhatsAppConfigurationConflictError(
                "secret encryption is unavailable",
            ) from exc

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise WhatsAppConfigurationConflictError(
                "WhatsApp configuration conflict",
            ) from exc

    @staticmethod
    def _to_domain(
        model: WhatsAppChannelConfigurationModel,
    ) -> WhatsAppChannelConfiguration:
        return WhatsAppChannelConfiguration(
            id=model.id,
            organization_id=model.organization_id,
            bot_id=model.bot_id,
            display_name=model.display_name,
            phone_number_id=model.phone_number_id,
            whatsapp_business_account_id=model.whatsapp_business_account_id,
            public_webhook_id=model.public_webhook_id,
            status=cast(WhatsAppChannelConfigurationStatus, model.status),
            webhook_enabled=model.webhook_enabled,
            verify_token_configured=model.verify_token_ciphertext is not None,
            access_token_configured=model.access_token_ciphertext is not None,
            app_secret_configured=model.app_secret_ciphertext is not None,
            created_by_user_id=model.created_by_user_id,
            updated_by_user_id=model.updated_by_user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
