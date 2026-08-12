from collections.abc import Generator

from app.application.automation_management.service import ManagedAutomationService
from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository


def get_managed_automation_service() -> Generator[ManagedAutomationService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        audit_writer = SqlAlchemyAuditRepository(session)
        plan_enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
        yield ManagedAutomationService(
            ManagedAutomationRepository(session),
            session,
            audit_writer,
            plan_enforcement=plan_enforcement,
            handoff=HumanHandoffService(
                HumanHandoffRepository(session),
                session,
                audit_writer,
                plan_enforcement,
            ),
        )
    finally:
        session_generator.close()
