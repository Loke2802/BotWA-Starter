from collections import Counter
from threading import Lock


class OnboardingMetricsRegistry:
    """Bounded counters without tenant, user, or resource labels."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[tuple[str, str]] = Counter()

    def record(self, metric: str, result: str) -> None:
        with self._lock:
            self._counters[(metric, result)] += 1

    def snapshot(self) -> dict[str, dict[tuple[str, str], int]]:
        with self._lock:
            return {"counters": dict(self._counters)}


onboarding_metrics = OnboardingMetricsRegistry()
