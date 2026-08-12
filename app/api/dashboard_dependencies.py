from collections.abc import Generator

from app.application.business_calendar.compatibility import (
    BusinessHoursStateCompatibilityService,
)
from app.application.business_calendar.service import BusinessCalendarService
from app.application.dashboard.business import DashboardBusinessStatusReader
from app.application.dashboard.metrics import DashboardMetrics
from app.application.dashboard.service import DashboardQueryService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from app.infrastructure.repositories.business_calendar_repository import (
    BusinessCalendarRepository,
)
from app.infrastructure.repositories.dashboard_repository import (
    SqlAlchemyDashboardRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository

_metrics = DashboardMetrics()


def get_dashboard_metrics() -> DashboardMetrics:
    return _metrics


def get_dashboard_query_service() -> Generator[DashboardQueryService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        plan_enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
        calendars = BusinessCalendarService(
            BusinessCalendarRepository(session),
            session,
            SqlAlchemyAuditRepository(session),
            plan_enforcement=plan_enforcement,
        )
        yield DashboardQueryService(
            SqlAlchemyDashboardRepository(session),
            DashboardBusinessStatusReader(
                calendars,
                BusinessHoursStateCompatibilityService(calendars, session),
            ),
            metrics=_metrics,
        )
    finally:
        session_generator.close()
