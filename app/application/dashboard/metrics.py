from collections import Counter
from threading import Lock


class DashboardMetrics:
    """Low-cardinality metrics; labels never contain tenant or user identity."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: Counter[tuple[str, str]] = Counter()
        self._errors: Counter[tuple[str, str]] = Counter()
        self._duration_ms: Counter[tuple[str, str]] = Counter()

    def record_request(self, endpoint: str, result: str, duration_ms: int) -> None:
        key = (endpoint, result)
        with self._lock:
            self._requests[key] += 1
            self._duration_ms[key] += max(0, duration_ms)

    def record_error(self, endpoint: str, result: str) -> None:
        with self._lock:
            self._errors[(endpoint, result)] += 1

    def snapshot(self) -> dict[str, dict[tuple[str, str], int]]:
        with self._lock:
            return {
                "dashboard_requests_total": dict(self._requests),
                "dashboard_request_duration_milliseconds": dict(self._duration_ms),
                "dashboard_query_errors_total": dict(self._errors),
            }
