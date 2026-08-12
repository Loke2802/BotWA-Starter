from collections.abc import Generator

from app.application.audit.metrics import AuditMetricsRegistry, audit_metrics
from app.application.audit.service import AuditCursorCodec, AuditQueryService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import get_settings


def get_audit_metrics() -> AuditMetricsRegistry:
    return audit_metrics


def get_audit_query_service() -> Generator[AuditQueryService]:
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield AuditQueryService(
            SqlAlchemyAuditRepository(session),
            cursor_codec=AuditCursorCodec(get_settings().auth_secret_key),
            metrics=audit_metrics,
            plan_enforcement=PlanEnforcementService(SqlAlchemyPlanRepository(session)),
        )
    finally:
        session_generator.close()
