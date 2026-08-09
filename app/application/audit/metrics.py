from collections import Counter
from threading import Lock


class AuditMetricsRegistry:
    """Low-cardinality in-process counters for PRD-017."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[tuple[str, str, str]] = Counter()
        self._duration_ms: Counter[tuple[str, str, str]] = Counter()

    def record(
        self,
        metric: str,
        *,
        operation: str,
        result: str,
        duration_ms: int = 0,
    ) -> None:
        key = (metric, operation, result)
        with self._lock:
            self._counts[key] += 1
            self._duration_ms[key] += max(0, duration_ms)

    def snapshot(self) -> dict[str, dict[tuple[str, str, str], int]]:
        with self._lock:
            return {
                "counters": dict(self._counts),
                "duration_milliseconds": dict(self._duration_ms),
            }


audit_metrics = AuditMetricsRegistry()
