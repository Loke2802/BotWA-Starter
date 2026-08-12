from collections import Counter
from threading import Lock


class BillingMetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[tuple[str, str]] = Counter()

    def record(self, metric: str, *, result: str) -> None:
        with self._lock:
            self._counts[(metric, result)] += 1

    def snapshot(self) -> dict[tuple[str, str], int]:
        with self._lock:
            return dict(self._counts)


billing_metrics = BillingMetricsRegistry()
