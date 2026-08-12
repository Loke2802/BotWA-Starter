"""PostgreSQL durable worker for approved managed automations."""

import argparse
import os
import time
from uuid import uuid4

from app.application.automation_management.service import ManagedAutomationService
from app.application.human_handoff.service import HumanHandoffService
from app.application.plans.service import PlanEnforcementService
from app.infrastructure.database import SessionLocal
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository


def run_batch(batch_size: int) -> int:
    session = SessionLocal()
    try:
        repository = ManagedAutomationRepository(session)
        audit_writer = SqlAlchemyAuditRepository(session)
        plan_enforcement = PlanEnforcementService(SqlAlchemyPlanRepository(session))
        rows = repository.claim(
            f"automation-worker-{os.getpid()}-{uuid4()}", batch_size, 60
        )
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
        return len(rows)
    finally:
        session.close()


def main() -> None:
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
