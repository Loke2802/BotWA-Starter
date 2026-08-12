from collections.abc import Generator

from app.application.business_calendar.metrics import BusinessCalendarMetrics
from app.application.business_calendar.service import BusinessCalendarService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository

_metrics = BusinessCalendarMetrics()


def get_business_calendar_metrics() -> BusinessCalendarMetrics:
    return _metrics


def get_business_calendar_service() -> Generator[BusinessCalendarService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield BusinessCalendarService(
            BusinessCalendarRepository(session),
            session,
            metrics=_metrics,
            audit_writer=SqlAlchemyAuditRepository(session),
            plan_enforcement=PlanEnforcementService(SqlAlchemyPlanRepository(session)),
        )
    finally:
        session_generator.close()
