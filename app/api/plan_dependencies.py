from collections.abc import Generator

from app.application.plans.metrics import plan_metrics
from app.application.plans.service import (
    PlanAssignmentService,
    PlanEnforcementService,
    PlanQueryService,
)
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository


def get_plan_services() -> (
    Generator[tuple[PlanQueryService, PlanAssignmentService, PlanEnforcementService]]
):
    session_generator = get_session()
    session = next(session_generator)
    try:
        repository = SqlAlchemyPlanRepository(session)
        enforcement = PlanEnforcementService(repository, metrics=plan_metrics)
        query = PlanQueryService(repository, enforcement, metrics=plan_metrics)
        assignment = PlanAssignmentService(
            repository,
            session,
            SqlAlchemyAuditRepository(session),
            query,
            metrics=plan_metrics,
        )
        yield query, assignment, enforcement
    finally:
        session_generator.close()


def get_plan_query_service() -> Generator[PlanQueryService]:
    services = get_plan_services()
    try:
        yield next(services)[0]
    finally:
        services.close()


def get_plan_assignment_service() -> Generator[PlanAssignmentService]:
    services = get_plan_services()
    try:
        yield next(services)[1]
    finally:
        services.close()


def get_plan_enforcement_service() -> Generator[PlanEnforcementService]:
    services = get_plan_services()
    try:
        yield next(services)[2]
    finally:
        services.close()
