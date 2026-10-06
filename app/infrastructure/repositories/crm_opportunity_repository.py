from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.crm.contracts import CrmNotFound
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_opportunity import (
    CrmStageModel,
    OpportunityActivityModel,
    OpportunityConversationModel,
    OpportunityHistoryModel,
    OpportunityModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.crm_identity import family


class OpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def contact(
        self, org: UUID, contact_id: UUID, *, lock: bool = False
    ) -> ContactModel:
        query = (
            select(ContactModel)
            .execution_options(populate_existing=True)
            .where(ContactModel.id == contact_id, ContactModel.organization_id == org)
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise CrmNotFound()
        return row

    def conversation(self, org: UUID, conversation_id: UUID) -> ConversationModel:
        row = self.session.scalar(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.organization_id == org,
                ConversationModel.management_status.is_not(None),
                ConversationModel.bot_id.is_not(None),
            )
        )
        if row is None:
            raise CrmNotFound()
        return row

    def organization(self, org: UUID, *, lock: bool = False) -> OrganizationModel:
        query = select(OrganizationModel).where(
            OrganizationModel.id == org, OrganizationModel.status == "active"
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise CrmNotFound()
        return row

    def validate_assignee(self, org: UUID, user_id: UUID) -> None:
        if (
            self.session.scalar(
                select(UserModel.id).where(
                    UserModel.id == user_id,
                    UserModel.organization_id == org,
                    UserModel.status == "active",
                )
            )
            is None
        ):
            raise ValueError("responsible must be an active member of this company")

    def stages(self, org: UUID) -> list[CrmStageModel]:
        return list(
            self.session.scalars(
                select(CrmStageModel)
                .where(CrmStageModel.organization_id == org)
                .order_by(CrmStageModel.position, CrmStageModel.code)
            )
        )

    def opportunity(
        self, org: UUID, opportunity_id: UUID, *, lock: bool = False
    ) -> OpportunityModel:
        query = (
            select(OpportunityModel)
            .where(
                OpportunityModel.id == opportunity_id,
                OpportunityModel.organization_id == org,
            )
            .execution_options(populate_existing=True)
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise CrmNotFound()
        return row

    def duplicate(self, org: UUID, actor: UUID, key: str) -> OpportunityModel | None:
        return self.session.scalar(
            select(OpportunityModel).where(
                OpportunityModel.organization_id == org,
                OpportunityModel.created_by_user_id == actor,
                OpportunityModel.idempotency_key == key,
            )
        )

    def page(
        self,
        org: UUID,
        *,
        contact_id: UUID | None,
        conversation_id: UUID | None,
        assigned_user_id: UUID | None,
        stage_code: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[OpportunityModel], int]:
        query = select(OpportunityModel).where(OpportunityModel.organization_id == org)
        if contact_id:
            query = query.where(
                OpportunityModel.contact_id.in_(family(self.session, org, contact_id))
            )
        if assigned_user_id:
            query = query.where(OpportunityModel.assigned_user_id == assigned_user_id)
        if stage_code:
            query = query.where(OpportunityModel.stage_code == stage_code)
        if conversation_id:
            query = query.join(
                OpportunityConversationModel,
                (OpportunityConversationModel.opportunity_id == OpportunityModel.id)
                & (OpportunityConversationModel.organization_id == org),
            ).where(OpportunityConversationModel.conversation_id == conversation_id)
        total = (
            self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = list(
            self.session.scalars(
                query.order_by(OpportunityModel.created_at.desc(), OpportunityModel.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, total

    def action(self, opportunity: OpportunityModel) -> OpportunityActivityModel | None:
        return self.session.scalar(
            select(OpportunityActivityModel).where(
                OpportunityActivityModel.organization_id == opportunity.organization_id,
                OpportunityActivityModel.opportunity_id == opportunity.id,
                OpportunityActivityModel.version == opportunity.version,
            )
        )

    def history(
        self, org: UUID, opportunity_id: UUID, page: int, page_size: int
    ) -> list[OpportunityHistoryModel]:
        return list(
            self.session.scalars(
                select(OpportunityHistoryModel)
                .where(
                    OpportunityHistoryModel.organization_id == org,
                    OpportunityHistoryModel.opportunity_id == opportunity_id,
                )
                .order_by(OpportunityHistoryModel.version.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
