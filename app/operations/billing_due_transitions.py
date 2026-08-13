"""One-shot PRD-019 due-transition job for an external deployment scheduler."""

import structlog

from app.application.billing.due_transitions import BillingDueTransitionProcessor
from app.infrastructure.billing.composition import build_billing_service
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.settings import get_settings

logger = structlog.get_logger(__name__)


def run_batch(batch_size: int | None = None) -> int:
    settings = get_settings()
    if not settings.billing_enabled:
        logger.info("billing_due_transition_job_disabled")
        return 0
    session = SessionLocal()
    try:
        service = build_billing_service(session, settings)
        result = BillingDueTransitionProcessor(
            BillingRepository(session), service, session
        ).process_due(batch_size=batch_size or settings.billing_due_batch_size)
        logger.info(
            "billing_due_transition_job_completed",
            examined=result.examined,
            succeeded=result.succeeded,
            retryable_failures=result.retryable_failures,
            skipped=result.skipped,
        )
        return 1 if result.retryable_failures else 0
    finally:
        session.close()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    raise SystemExit(run_batch())


if __name__ == "__main__":
    main()
