import time
from collections import deque
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.domain.integration.contracts import (
    Capability,
    IntegrationEvent,
    ProviderStatus,
)


@dataclass
class LatencyStats:
    last: float = 0.0
    total: float = 0.0
    count: int = 0
    recent: deque[float] = field(default_factory=lambda: deque[float](maxlen=100))

    @property
    def avg(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total / self.count

    @property
    def p50(self) -> float:
        if not self.recent:
            return 0.0
        sorted_vals = sorted(self.recent)
        return sorted_vals[len(sorted_vals) // 2]

    @property
    def p95(self) -> float:
        if not self.recent:
            return 0.0
        sorted_vals = sorted(self.recent)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    @property
    def p99(self) -> float:
        if not self.recent:
            return 0.0
        sorted_vals = sorted(self.recent)
        idx = int(len(sorted_vals) * 0.99)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def record(self, latency_ms: float) -> None:
        self.last = latency_ms
        self.total += latency_ms
        self.count += 1
        self.recent.append(latency_ms)


@dataclass
class ProviderMetrics:
    provider_id: str = ""
    total_requests: int = 0
    total_failures: int = 0
    total_retries: int = 0
    circuit_breaker_trips: int = 0
    rate_limit_hits: int = 0
    latency: LatencyStats = field(default_factory=LatencyStats)
    last_health_status: ProviderStatus = ProviderStatus.ACTIVE
    last_health_error: str | None = None
    last_health_at: float = 0.0


class IntegrationMonitor:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderMetrics] = {}
        self._events: list[IntegrationEvent] = []

    def _get_or_create(self, provider_id: str) -> ProviderMetrics:
        if provider_id not in self._providers:
            self._providers[provider_id] = ProviderMetrics(provider_id=provider_id)
        return self._providers[provider_id]

    def record_request(
        self,
        provider_id: str,
        capability: Capability,
        success: bool,
        latency_ms: int,
        attempt: int,
    ) -> None:
        metrics = self._get_or_create(provider_id)
        metrics.total_requests += 1
        if not success:
            metrics.total_failures += 1
        if attempt > 1:
            metrics.total_retries += attempt - 1
        metrics.latency.record(float(latency_ms))

    def record_rate_limit_hit(self, provider_id: str) -> None:
        self._get_or_create(provider_id).rate_limit_hits += 1

    def record_circuit_breaker_trip(self, provider_id: str) -> None:
        self._get_or_create(provider_id).circuit_breaker_trips += 1

    def record_health(
        self,
        provider_id: str,
        status: ProviderStatus,
        error: str | None = None,
    ) -> None:
        metrics = self._get_or_create(provider_id)
        metrics.last_health_status = status
        metrics.last_health_error = error
        metrics.last_health_at = time.monotonic()

    def get_metrics(self, provider_id: str) -> ProviderMetrics | None:
        return self._providers.get(provider_id)

    def get_all_metrics(self) -> dict[str, ProviderMetrics]:
        return dict(self._providers)

    def get_summary(self) -> dict[str, object]:
        total_req = sum(m.total_requests for m in self._providers.values())
        total_fail = sum(m.total_failures for m in self._providers.values())
        total_retry = sum(m.total_retries for m in self._providers.values())
        return {
            "total_requests": total_req,
            "total_failures": total_fail,
            "total_retries": total_retry,
            "providers": len(self._providers),
            "healthy_providers": sum(
                1
                for m in self._providers.values()
                if m.last_health_status == ProviderStatus.ACTIVE
            ),
        }

    def add_event(self, event: IntegrationEvent) -> None:
        self._events.append(event)

    def get_events(self, limit: int = 100) -> list[IntegrationEvent]:
        return self._events[-limit:]

    def create_event(
        self,
        event_type: str,
        capability: Capability,
        provider_id: str,
        tenant_id: str,
        request_id: UUID,
        success: bool,
        latency_ms: int = 0,
        attempt: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> IntegrationEvent:
        event = IntegrationEvent(
            event_id=uuid4(),
            event_type=event_type,
            capability=capability,
            provider_id=provider_id,
            tenant_id=tenant_id,
            request_id=request_id,
            success=success,
            latency_ms=latency_ms,
            attempt=attempt,
            error=None,
        )
        self.add_event(event)
        return event
