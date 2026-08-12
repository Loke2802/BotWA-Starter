from datetime import UTC, datetime
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.plans.contracts import (
    PlanAssignment,
    PlanConfiguration,
    PlanDefinition,
    PlanLimitKey,
    PlanStatus,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_calendar import BusinessCalendarModel
from app.infrastructure.models.integration_management import IntegrationConnectionModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)

PLAN_STATUS_ADAPTER: TypeAdapter[PlanStatus] = TypeAdapter(PlanStatus)


class SqlAlchemyPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_organization(self, organization_id: UUID) -> bool:
        statement = (
            select(OrganizationModel.id)
            .where(OrganizationModel.id == organization_id)
            .with_for_update()
        )
        return self.session.execute(statement).scalar_one_or_none() is not None

    def organization_status(self, organization_id: UUID) -> str | None:
        return self.session.execute(
            select(OrganizationModel.status).where(
                OrganizationModel.id == organization_id
            )
        ).scalar_one_or_none()

    def get_plan_by_code(self, plan_code: str) -> PlanDefinition | None:
        row = self.session.scalars(
            select(PlanDefinitionModel).where(
                PlanDefinitionModel.plan_code == plan_code
            )
        ).first()
        return self._plan(row) if row is not None else None

    def get_plan_by_id(self, plan_id: UUID) -> PlanDefinition | None:
        row = self.session.get(PlanDefinitionModel, plan_id)
        return self._plan(row) if row is not None else None

    def get_assignment(self, organization_id: UUID) -> PlanAssignment | None:
        row = self.session.get(OrganizationPlanAssignmentModel, organization_id)
        return self._assignment(row) if row is not None else None

    def assignment_model(
        self, organization_id: UUID
    ) -> OrganizationPlanAssignmentModel | None:
        return self.session.get(OrganizationPlanAssignmentModel, organization_id)

    def create_default_assignment(self, organization_id: UUID) -> None:
        plan = self.session.scalars(
            select(PlanDefinitionModel).where(
                PlanDefinitionModel.plan_code == "default"
            )
        ).first()
        if plan is None:
            raise RuntimeError("default plan is unavailable")
        now = datetime.now(UTC)
        self.session.add(
            OrganizationPlanAssignmentModel(
                organization_id=organization_id,
                plan_definition_id=plan.id,
                version=1,
                assigned_by_user_id=None,
                created_at=now,
                updated_at=now,
            )
        )

    def resource_count(self, organization_id: UUID, key: PlanLimitKey) -> int:
        if key == "max_active_bots":
            statement = (
                select(func.count())
                .select_from(BotModel)
                .where(
                    BotModel.organization_id == organization_id,
                    BotModel.status == "active",
                )
            )
        elif key == "max_active_users":
            statement = (
                select(func.count())
                .select_from(UserModel)
                .where(
                    UserModel.organization_id == organization_id,
                    UserModel.status == "active",
                )
            )
        elif key == "max_integrations":
            statement = (
                select(func.count())
                .select_from(IntegrationConnectionModel)
                .where(
                    IntegrationConnectionModel.organization_id == organization_id,
                    IntegrationConnectionModel.status != "archived",
                )
            )
        elif key == "max_automations":
            statement = (
                select(func.count())
                .select_from(ManagedAutomationDefinitionModel)
                .where(
                    ManagedAutomationDefinitionModel.organization_id == organization_id,
                    ManagedAutomationDefinitionModel.status != "archived",
                )
            )
        elif key == "max_business_calendars":
            statement = (
                select(func.count())
                .select_from(BusinessCalendarModel)
                .where(
                    BusinessCalendarModel.organization_id == organization_id,
                    BusinessCalendarModel.status != "archived",
                )
            )
        elif key == "max_whatsapp_configurations":
            statement = (
                select(func.count())
                .select_from(WhatsAppChannelConfigurationModel)
                .where(
                    WhatsAppChannelConfigurationModel.organization_id == organization_id
                )
            )
        else:
            statement = (
                select(func.count())
                .select_from(KnowledgeEntryModel)
                .where(
                    KnowledgeEntryModel.organization_id == organization_id,
                    KnowledgeEntryModel.status != "archived",
                )
            )
        return int(self.session.execute(statement).scalar_one())

    @staticmethod
    def _plan(row: PlanDefinitionModel) -> PlanDefinition:
        return PlanDefinition(
            id=row.id,
            plan_code=row.plan_code,
            display_name=row.display_name,
            status=PLAN_STATUS_ADAPTER.validate_python(row.status),
            configuration=PlanConfiguration.model_validate(row.configuration),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _assignment(row: OrganizationPlanAssignmentModel) -> PlanAssignment:
        return PlanAssignment(
            organization_id=row.organization_id,
            plan_definition_id=row.plan_definition_id,
            version=row.version,
            assigned_by_user_id=row.assigned_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
