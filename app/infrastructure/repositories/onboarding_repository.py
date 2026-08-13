from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import case, exists, or_, select
from sqlalchemy.orm import Session

from app.application.onboarding.repository import (
    BotSnapshot,
    IntegrationSnapshot,
    KnowledgeSnapshot,
    OrganizationSnapshot,
    PlanSnapshot,
    WhatsAppSnapshot,
)
from app.domain.business_configuration.contracts import BusinessConfiguration
from app.domain.plans.contracts import PlanConfiguration
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel
from app.infrastructure.models.integration_management import (
    IntegrationConnectionModel,
    IntegrationCredentialModel,
)
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.onboarding import OrganizationOnboardingModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)


class SqlAlchemyOnboardingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, organization_id: UUID) -> OrganizationOnboardingModel | None:
        return self.session.get(OrganizationOnboardingModel, organization_id)

    def get_for_update(
        self, organization_id: UUID
    ) -> OrganizationOnboardingModel | None:
        return self.session.scalars(
            select(OrganizationOnboardingModel)
            .where(OrganizationOnboardingModel.organization_id == organization_id)
            .with_for_update()
        ).one_or_none()

    def add(self, workflow: OrganizationOnboardingModel) -> None:
        self.session.add(workflow)

    def lock_organization(self, organization_id: UUID) -> bool:
        return (
            self.session.execute(
                select(OrganizationModel.id)
                .where(OrganizationModel.id == organization_id)
                .with_for_update()
            ).scalar_one_or_none()
            is not None
        )

    def organization(self, organization_id: UUID) -> OrganizationSnapshot | None:
        row = self.session.get(OrganizationModel, organization_id)
        if row is None:
            return None
        return OrganizationSnapshot(
            id=row.id,
            name=row.name,
            slug=row.slug,
            status=row.status,
            settings=row.settings,
            created_at=row.created_at,
            updated_at=row.updated_at,
            deactivated_at=row.deactivated_at,
        )

    def has_active_owner(self, organization_id: UUID) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        UserModel.organization_id == organization_id,
                        UserModel.status == "active",
                        UserModel.role == "organization_owner",
                    )
                )
            )
        )

    def plan(self, organization_id: UUID) -> PlanSnapshot:
        row = self.session.execute(
            select(OrganizationPlanAssignmentModel, PlanDefinitionModel)
            .outerjoin(
                PlanDefinitionModel,
                PlanDefinitionModel.id
                == OrganizationPlanAssignmentModel.plan_definition_id,
            )
            .where(OrganizationPlanAssignmentModel.organization_id == organization_id)
        ).first()
        if row is None:
            return PlanSnapshot(False, False, None, None)
        assignment, plan = row
        if plan is None:
            return PlanSnapshot(True, False, None, None)
        try:
            configuration = PlanConfiguration.model_validate(plan.configuration)
        except ValidationError:
            configuration = None
        return PlanSnapshot(True, True, plan.status, configuration)

    def initial_bot(self, organization_id: UUID) -> BotSnapshot | None:
        any_bot = bool(
            self.session.scalar(
                select(exists().where(BotModel.organization_id == organization_id))
            )
        )
        rows = self.session.execute(
            select(BotModel, BusinessConfigurationModel)
            .outerjoin(
                BusinessConfigurationModel,
                BusinessConfigurationModel.bot_id == BotModel.id,
            )
            .where(
                BotModel.organization_id == organization_id,
                BotModel.status == "active",
            )
            .order_by(BotModel.created_at, BotModel.id)
        ).all()
        if not rows:
            if not any_bot:
                return None
            inactive_bot_id = self.session.scalar(
                select(BotModel.id)
                .where(BotModel.organization_id == organization_id)
                .order_by(BotModel.created_at, BotModel.id)
                .limit(1)
            )
            if inactive_bot_id is None:
                return None
            return BotSnapshot(
                id=inactive_bot_id,
                status="inactive",
                business_configuration_id=None,
                business_configuration_status=None,
                business_configuration_valid=False,
                any_bot_exists=True,
            )
        selected_bot, selected_configuration = rows[0]
        selected_configuration_valid = self._business_configuration_valid(
            selected_configuration
        )
        for candidate_bot, candidate_configuration in rows:
            candidate_valid = self._business_configuration_valid(
                candidate_configuration
            )
            if (
                candidate_configuration is not None
                and candidate_configuration.status == "configured"
                and candidate_valid
            ):
                selected_bot = candidate_bot
                selected_configuration = candidate_configuration
                selected_configuration_valid = True
                break
        return BotSnapshot(
            id=selected_bot.id,
            status=selected_bot.status,
            business_configuration_id=(
                selected_configuration.id
                if selected_configuration is not None
                else None
            ),
            business_configuration_status=(
                selected_configuration.status
                if selected_configuration is not None
                else None
            ),
            business_configuration_valid=selected_configuration_valid,
            any_bot_exists=any_bot,
        )

    @staticmethod
    def _business_configuration_valid(
        configuration: BusinessConfigurationModel | None,
    ) -> bool:
        if configuration is not None:
            try:
                BusinessConfiguration.model_validate(
                    {
                        "id": configuration.id,
                        "bot_id": configuration.bot_id,
                        "business_name": configuration.business_name,
                        "description": configuration.description,
                        "phone": configuration.phone,
                        "email": configuration.email,
                        "website": configuration.website,
                        "address": configuration.address,
                        "timezone": configuration.timezone,
                        "business_hours": configuration.business_hours,
                        "services": configuration.services,
                        "payment_methods": configuration.payment_methods,
                        "policies": configuration.policies,
                        "service_instructions": configuration.service_instructions,
                        "handoff_enabled": configuration.handoff_enabled,
                        "handoff_message": configuration.handoff_message,
                        "handoff_keywords": configuration.handoff_keywords,
                        "handoff_outside_business_hours": (
                            configuration.handoff_outside_business_hours
                        ),
                        "status": configuration.status,
                        "created_at": configuration.created_at,
                        "updated_at": configuration.updated_at,
                    }
                )
                return True
            except ValidationError:
                return False
        return False

    def whatsapp(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> WhatsAppSnapshot | None:
        if bot_id is None:
            return None
        row = self.session.execute(
            select(
                WhatsAppChannelConfigurationModel.id,
                WhatsAppChannelConfigurationModel.status,
                WhatsAppChannelConfigurationModel.webhook_enabled,
                WhatsAppChannelConfigurationModel.verify_token_ciphertext.is_not(None),
                WhatsAppChannelConfigurationModel.access_token_ciphertext.is_not(None),
                WhatsAppChannelConfigurationModel.app_secret_ciphertext.is_not(None),
            )
            .where(
                WhatsAppChannelConfigurationModel.organization_id == organization_id,
                WhatsAppChannelConfigurationModel.bot_id == bot_id,
            )
            .order_by(
                case(
                    (WhatsAppChannelConfigurationModel.status == "active", 0),
                    else_=1,
                ),
                WhatsAppChannelConfigurationModel.created_at,
                WhatsAppChannelConfigurationModel.id,
            )
            .limit(1)
        ).first()
        if row is None:
            return None
        return WhatsAppSnapshot(
            id=row[0],
            status=row[1],
            webhook_enabled=row[2],
            verify_token_configured=row[3],
            access_token_configured=row[4],
            app_secret_configured=row[5],
        )

    def knowledge(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> KnowledgeSnapshot:
        if bot_id is None:
            return KnowledgeSnapshot(None)
        entry_id = self.session.scalar(
            select(KnowledgeEntryModel.id)
            .where(
                KnowledgeEntryModel.organization_id == organization_id,
                KnowledgeEntryModel.bot_id == bot_id,
                KnowledgeEntryModel.status == "published",
            )
            .order_by(KnowledgeEntryModel.created_at, KnowledgeEntryModel.id)
            .limit(1)
        )
        return KnowledgeSnapshot(entry_id)

    def integration(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> IntegrationSnapshot:
        scope = [IntegrationConnectionModel.organization_id == organization_id]
        if bot_id is not None:
            scope.append(
                or_(
                    IntegrationConnectionModel.bot_id.is_(None),
                    IntegrationConnectionModel.bot_id == bot_id,
                )
            )
        any_connection = bool(
            self.session.scalar(
                select(
                    exists().where(
                        *scope,
                        IntegrationConnectionModel.status != "archived",
                    )
                )
            )
        )
        row = self.session.execute(
            select(
                IntegrationConnectionModel.id,
                IntegrationConnectionModel.status,
                IntegrationCredentialModel.id.is_not(None),
                IntegrationConnectionModel.health_status,
                IntegrationConnectionModel.last_health_checked_at.is_not(None),
            )
            .outerjoin(
                IntegrationCredentialModel,
                IntegrationCredentialModel.integration_connection_id
                == IntegrationConnectionModel.id,
            )
            .where(*scope, IntegrationConnectionModel.status != "archived")
            .order_by(
                case((IntegrationConnectionModel.status == "active", 0), else_=1),
                IntegrationConnectionModel.created_at,
                IntegrationConnectionModel.id,
            )
            .limit(1)
        ).first()
        if row is None:
            return IntegrationSnapshot(None, None, False, None, False, any_connection)
        return IntegrationSnapshot(
            id=row[0],
            status=row[1],
            has_credentials=row[2],
            health_status=row[3],
            health_checked=row[4],
            any_connection_exists=any_connection,
        )
