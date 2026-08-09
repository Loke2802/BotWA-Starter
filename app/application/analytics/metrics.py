from collections import Counter
from threading import Lock


class AnalyticsMetricsRegistry:
    """In-process, low-cardinality PRD-016 observability registry."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[tuple[str, str, str]] = Counter()
        self._durations_ms: Counter[tuple[str, str, str]] = Counter()

    def record(
        self, metric: str, operation: str, result: str, duration_ms: int
    ) -> None:
        key = (metric, operation, result)
        with self._lock:
            self._counters[key] += 1
            self._durations_ms[key] += max(0, duration_ms)

    def snapshot(self) -> dict[str, dict[tuple[str, str, str], int]]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "duration_milliseconds": dict(self._durations_ms),
            }
