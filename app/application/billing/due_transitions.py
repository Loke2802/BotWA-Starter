from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from app.application.billing.metrics import BillingMetricsRegistry, billing_metrics
from app.application.billing.service import BillingService
from app.domain.billing.contracts import BillingDueTransitionResult
from app.infrastructure.repositories.billing_repository import BillingRepository

logger = structlog.get_logger(__name__)


class BillingDueTransitionProcessor:
    def __init__(
        self,
        repository: BillingRepository,
        service: BillingService,
        session: Session,
        *,
        metrics: BillingMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.session = session
        self.metrics = metrics or billing_metrics

    def process_due(
        self, *, now: datetime | None = None, batch_size: int
    ) -> BillingDueTransitionResult:
        if not 1 <= batch_size <= 1_000:
            raise ValueError("batch_size must be between 1 and 1000")
        effective_now = now or datetime.now(UTC)
        if not self.service.enabled:
            return BillingDueTransitionResult(
                examined=0, succeeded=0, retryable_failures=0, skipped=0
            )
        candidates = self.repository.due_transition_candidates(
            effective_now, limit=batch_size
        )
        succeeded = 0
        retryable_failures = 0
        skipped = 0
        for candidate in candidates:
            try:
                operation = self.service.process_due_transition(
                    candidate.organization_id,
                    candidate.subscription_id,
                    now=effective_now,
                )
            except Exception as exc:
                self.session.rollback()
                retryable_failures += 1
                self.metrics.record_due(
                    operation=candidate.operation, result="retryable_failure"
                )
                logger.warning(
                    "billing_due_transition_retryable_failure",
                    operation=candidate.operation,
                    safe_error_code=getattr(
                        exc, "safe_code", "BILLING_PROCESSING_FAILED"
                    ),
                )
                continue
            if operation is None:
                skipped += 1
                self.metrics.record_due(operation=candidate.operation, result="skipped")
                continue
            succeeded += 1
            self.metrics.record_due(operation=operation, result="success")
            logger.info("billing_due_transition_completed", operation=operation)
        return BillingDueTransitionResult(
            examined=len(candidates),
            succeeded=succeeded,
            retryable_failures=retryable_failures,
            skipped=skipped,
        )
