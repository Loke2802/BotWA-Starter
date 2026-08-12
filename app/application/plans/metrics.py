from collections import Counter
from threading import Lock


class PlanMetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[tuple[str, str, str]] = Counter()

    def record(self, metric: str, *, operation: str, result: str) -> None:
        with self._lock:
            self._counts[(metric, operation, result)] += 1

    def snapshot(self) -> dict[tuple[str, str, str], int]:
        with self._lock:
            return dict(self._counts)


plan_metrics = PlanMetricsRegistry()
