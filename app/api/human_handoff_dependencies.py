from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository


def get_human_handoff_service(
    session: Annotated[Session, Depends(get_session)],
) -> HumanHandoffService:
    return HumanHandoffService(
        HumanHandoffRepository(session),
        session,
        SqlAlchemyAuditRepository(session),
        PlanEnforcementService(SqlAlchemyPlanRepository(session)),
    )
