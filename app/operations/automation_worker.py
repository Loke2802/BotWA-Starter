"""PostgreSQL durable worker for approved managed automations."""

import argparse
import os
import time
from time import perf_counter
from uuid import uuid4

import structlog

from app.application.automation_management.service import ManagedAutomationService
from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from app.observability.metrics import safe_metric

logger = structlog.get_logger(__name__)


def run_batch(batch_size: int) -> int:
    with correlation_context():
        started = perf_counter()
        session = SessionLocal()
        try:
            repository = ManagedAutomationRepository(session)
            audit_writer = SqlAlchemyAuditRepository(session)
            plan_enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
            rows = repository.claim(
                f"automation-worker-{os.getpid()}-{uuid4()}", batch_size, 60
            )
            logger.info(
                "operation_started",
                operation="automation_worker_batch",
                claimed=len(rows),
            )
            for _row in rows:
                safe_metric("record_automation", "claimed")
            service = ManagedAutomationService(
                repository,
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
            for row in rows:
                service.run(row)
            logger.info(
                "operation_completed",
                operation="automation_worker_batch",
                claimed=len(rows),
                completed=sum(row.status == "succeeded" for row in rows),
                failed=sum(row.status == "failed" for row in rows),
                skipped=sum(row.status == "skipped" for row in rows),
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            return len(rows)
        except Exception:
            logger.error(
                "operation_failed",
                operation="automation_worker_batch",
                error_code="UNEXPECTED_ERROR",
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            raise
        finally:
            session.close()


def main() -> None:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()
    while True:
        count = run_batch(args.batch_size)
        if args.once:
            return
        if count == 0:
            time.sleep(1)


if __name__ == "__main__":
    main()
