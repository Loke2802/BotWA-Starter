from collections import Counter
from threading import Lock

from app.observability.metrics import safe_metric


class BillingMetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[tuple[str, ...]] = Counter()

    def record(self, metric: str, *, result: str) -> None:
        with self._lock:
            self._counts[(metric, result)] += 1
        operation = {
            "billing_checkout_total": "checkout",
            "billing_plan_changes_total": "plan_change",
            "billing_cancellations_total": "cancellation",
            "billing_reconciliations_total": "reconciliation",
            "billing_webhook_events_total": "webhook",
        }.get(metric)
        if operation is not None:
            safe_metric("record_billing", operation, result)

    def record_due(self, *, operation: str, result: str) -> None:
        with self._lock:
            self._counts[("billing_due_transitions_total", operation, result)] += 1
        safe_metric("record_billing", f"due_{operation}", result)

    def snapshot(self) -> dict[tuple[str, ...], int]:
        with self._lock:
            return dict(self._counts)


billing_metrics = BillingMetricsRegistry()
