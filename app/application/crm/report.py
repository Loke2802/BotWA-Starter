"""Bounded SQL aggregates; each currency is reported independently."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, null, select

from app.application.crm.service import OpportunityService
from app.domain.crm.customer_contracts import CommercialMetric, CommercialReport
from app.domain.user.contracts import User
from app.infrastructure.models.crm_opportunity import CrmStageModel, OpportunityModel
from app.security.authorization import has_permission


class CommercialReportService:
    def __init__(self, commercial: OpportunityService) -> None:
        self.commercial = commercial

    def report(
        self,
        org: UUID,
        actor: User,
        date_from: datetime | None,
        date_to: datetime | None,
        assigned: UUID | None,
    ) -> CommercialReport:
        self.commercial._read(org, actor)
        organization = self.commercial.repository.organization(org)
        if any(
            d is not None and d.utcoffset() is None for d in (date_from, date_to)
        ) or (date_from and date_to and date_from >= date_to):
            raise ValueError("Use an aware half-open date range")
        content = has_permission(actor, "crm.opportunities.read_content")
        currency = (
            OpportunityModel.currency
            if content
            else func.cast(null(), OpportunityModel.currency.type)
        ).label("currency")
        query = (
            select(
                OpportunityModel.assigned_user_id,
                CrmStageModel.kind,
                currency,
                func.count(OpportunityModel.id),
                (
                    func.sum(OpportunityModel.amount)
                    if content
                    else func.cast(null(), OpportunityModel.amount.type)
                ).label("amount"),
            )
            .join(
                CrmStageModel,
                (CrmStageModel.organization_id == OpportunityModel.organization_id)
                & (CrmStageModel.code == OpportunityModel.stage_code),
            )
            .where(OpportunityModel.organization_id == org)
        )
        if date_from:
            query = query.where(OpportunityModel.created_at >= date_from)
        if date_to:
            query = query.where(OpportunityModel.created_at < date_to)
        if assigned:
            query = query.where(OpportunityModel.assigned_user_id == assigned)
        rows = self.commercial.session.execute(
            query.group_by(
                OpportunityModel.assigned_user_id, CrmStageModel.kind, currency
            ).order_by(OpportunityModel.assigned_user_id, CrmStageModel.kind, currency)
        ).all()
        return CommercialReport(
            date_from=date_from,
            date_to=date_to,
            timezone=str(organization.settings.get("timezone") or "UTC"),
            can_read_amounts=content,
            items=[
                CommercialMetric(
                    assigned_user_id=assigned,
                    kind=kind,
                    currency=curr,
                    count=count,
                    amount=amount,
                )
                for assigned, kind, curr, count, amount in rows
            ],
        )
