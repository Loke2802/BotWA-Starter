from collections import Counter
from threading import Lock

from app.observability.metrics import safe_metric


class OnboardingMetricsRegistry:
    """Bounded counters without tenant, user, or resource labels."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[tuple[str, str]] = Counter()

    def record(self, metric: str, result: str) -> None:
        with self._lock:
            self._counters[(metric, result)] += 1
        operation = {
            "onboarding_started_total": "start",
            "onboarding_completion_attempts_total": "complete",
            "onboarding_readiness_reads_total": "readiness",
        }.get(metric)
        if operation is not None:
            safe_metric("record_onboarding", operation, result)

    def snapshot(self) -> dict[str, dict[tuple[str, str], int]]:
        with self._lock:
            return {"counters": dict(self._counters)}


onboarding_metrics = OnboardingMetricsRegistry()
