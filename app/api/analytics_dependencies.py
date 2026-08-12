from collections.abc import Generator

from app.application.analytics.metrics import AnalyticsMetricsRegistry
from app.application.analytics.service import (
    AnalyticsProjectionService,
    AnalyticsQueryService,
)
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.analytics_repository import (
    SqlAlchemyAnalyticsRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository

_metrics = AnalyticsMetricsRegistry()


def get_analytics_metrics() -> AnalyticsMetricsRegistry:
    return _metrics


def get_analytics_query_service() -> Generator[AnalyticsQueryService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield AnalyticsQueryService(
            SqlAlchemyAnalyticsRepository(session),
            metrics=_metrics,
            plan_enforcement=PlanEnforcementService(SqlAlchemyPlanRepository(session)),
        )
    finally:
        session_generator.close()


def get_analytics_projection_service() -> Generator[AnalyticsProjectionService]:
    """Internal/admin application boundary; deliberately not exposed as HTTP."""
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield AnalyticsProjectionService(
            SqlAlchemyAnalyticsRepository(session), metrics=_metrics
        )
    finally:
        session_generator.close()
