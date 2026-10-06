"""Read-only commercial queue. Current pending actions only; tenant scope in SQL."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.application.crm.presentation import record
from app.domain.crm.contracts import FollowUpFilter, FollowUpList, FollowUpSummary
from app.domain.user.contracts import User
from app.infrastructure.models.crm_opportunity import (
    CrmStageModel,
    OpportunityActivityModel,
    OpportunityModel,
)
from app.infrastructure.repositories.crm_opportunity_repository import (
    OpportunityRepository,
)
from app.security.authorization import has_permission, require_scoped_permission
from app.security.secret_cipher import SecretCipher


class FollowUpService:
    def __init__(self, session: Session, cipher: SecretCipher) -> None:
        self.session = session
        self.cipher = cipher
        self.repository = OpportunityRepository(session)

    def list(
        self,
        org: UUID,
        actor: User,
        *,
        due: FollowUpFilter = "all",
        assigned_user_id: UUID | None = None,
        stage_code: str | None = None,
        page: int = 1,
        page_size: int = 20,
        as_of: datetime | None = None,
    ) -> FollowUpList:
        require_scoped_permission(actor, "crm.opportunities.read", org)
        require_scoped_permission(actor, "contacts.read", org)
        organization = self.repository.organization(org)
        instant = as_of or datetime.now(UTC)
        if instant.utcoffset() is None:
            raise ValueError("timezone required")
        if due not in {"all", "overdue", "upcoming", "without_action"}:
            raise ValueError("unknown follow-up filter")
        op, action, stage = OpportunityModel, OpportunityActivityModel, CrmStageModel
        query = (
            select(op)
            .join(
                stage,
                and_(
                    stage.organization_id == op.organization_id,
                    stage.code == op.stage_code,
                ),
            )
            .outerjoin(
                action,
                and_(
                    action.organization_id == op.organization_id,
                    action.opportunity_id == op.id,
                    action.version == op.version,
                    action.status == "pending",
                ),
            )
            .where(op.organization_id == org, stage.kind == "open")
        )
        if assigned_user_id:
            query = query.where(op.assigned_user_id == assigned_user_id)
        if stage_code:
            query = query.where(op.stage_code == stage_code)
        predicates = {
            "overdue": action.due_at < instant,
            "upcoming": action.due_at >= instant,
            "without_action": action.id.is_(None),
        }
        # Counters share the stage/owner scope; selecting a due bucket does not
        # change the other counters. One instant drives all deadline comparisons.
        values = self.session.execute(
            query.with_only_columns(
                func.count(op.id),
                *(
                    func.coalesce(func.sum(case((p, 1), else_=0)), 0)
                    for p in predicates.values()
                ),
            )
        ).one()
        summary = FollowUpSummary(
            open=values[0],
            overdue=values[1],
            upcoming=values[2],
            without_action=values[3],
        )
        if due != "all":
            query = query.where(predicates[due])
        total = summary.open if due == "all" else getattr(summary, due)
        rows = self.session.scalars(
            query.order_by(action.due_at.asc().nulls_last(), op.created_at, op.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return FollowUpList(
            items=[
                record(
                    self.repository,
                    self.cipher,
                    row,
                    content=has_permission(actor, "crm.opportunities.read_content"),
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            as_of=instant,
            timezone=str(organization.settings.get("timezone") or "UTC"),
            summary=summary,
        )
