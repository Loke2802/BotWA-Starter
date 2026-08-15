"""One-shot PRD-019 due-transition job for an external deployment scheduler."""

from time import perf_counter

import structlog

from app.application.billing.due_transitions import BillingDueTransitionProcessor
from app.infrastructure.billing.composition import build_billing_service
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context

logger = structlog.get_logger(__name__)


def run_batch(batch_size: int | None = None) -> int:
    with correlation_context():
        started = perf_counter()
        logger.info("operation_started", operation="billing_due_transitions")
        settings = get_settings()
        if not settings.billing_enabled:
            logger.info("billing_due_transition_job_disabled")
            logger.info(
                "operation_completed",
                operation="billing_due_transitions",
                examined=0,
                succeeded=0,
                retryable_failed=0,
                skipped=0,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
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
            logger.info(
                "operation_completed",
                operation="billing_due_transitions",
                examined=result.examined,
                succeeded=result.succeeded,
                retryable_failed=result.retryable_failures,
                skipped=result.skipped,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            return 1 if result.retryable_failures else 0
        except Exception:
            logger.error(
                "operation_failed",
                operation="billing_due_transitions",
                error_code="UNEXPECTED_ERROR",
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            raise
        finally:
            session.close()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    raise SystemExit(run_batch())


if __name__ == "__main__":
    main()
