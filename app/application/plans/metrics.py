from collections import Counter
from threading import Lock

from app.observability.metrics import safe_metric


class PlanMetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[tuple[str, str, str]] = Counter()

    def record(self, metric: str, *, operation: str, result: str) -> None:
        with self._lock:
            self._counts[(metric, operation, result)] += 1
        safe_metric("record_plan", metric, operation, result)

    def snapshot(self) -> dict[tuple[str, str, str], int]:
        with self._lock:
            return dict(self._counts)


plan_metrics = PlanMetricsRegistry()
