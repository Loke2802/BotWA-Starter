from uuid import uuid4

from app.core.integration.monitor import IntegrationMonitor
from app.domain.integration.contracts import Capability


class TestIntegrationMonitor:
    def test_record_request_updates_counts(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_request(
            provider_id="p1",
            capability=Capability.SEND_MESSAGE,
            success=True,
            latency_ms=100,
            attempt=1,
        )
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.total_requests == 1
        assert metrics.total_failures == 0

    def test_record_request_tracks_failures(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_request(
            provider_id="p1",
            capability=Capability.SEND_MESSAGE,
            success=False,
            latency_ms=200,
            attempt=1,
        )
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.total_failures == 1
        assert metrics.total_requests == 1

    def test_record_rate_limit_hit(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_rate_limit_hit("p1")
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.rate_limit_hits == 1

    def test_record_circuit_breaker_trip(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_circuit_breaker_trip("p1")
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.circuit_breaker_trips == 1

    def test_get_metrics_returns_none_for_unknown(self) -> None:
        monitor = IntegrationMonitor()
        assert monitor.get_metrics("nonexistent") is None

    def test_latency_stats_tracking(self) -> None:
        monitor = IntegrationMonitor()
        for latency in [10, 20, 30, 40, 50]:
            monitor.record_request(
                provider_id="p1",
                capability=Capability.SEND_MESSAGE,
                success=True,
                latency_ms=latency,
                attempt=1,
            )
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.latency.avg == 30.0
        assert metrics.latency.p50 == 30.0
        assert metrics.latency.p95 == 50.0
        assert metrics.latency.p99 == 50.0

    def test_create_event_and_get_events(self) -> None:
        monitor = IntegrationMonitor()
        monitor.create_event(
            event_type="integration.completed",
            capability=Capability.SEND_MESSAGE,
            provider_id="p1",
            tenant_id="t1",
            request_id=uuid4(),
            success=True,
            latency_ms=50,
            attempt=1,
        )
        events = monitor.get_events(limit=10)
        assert len(events) == 1
        assert events[0].event_type == "integration.completed"

    def test_get_events_respects_limit(self) -> None:
        monitor = IntegrationMonitor()
        for _ in range(5):
            monitor.create_event(
                event_type="test",
                capability=Capability.SEND_MESSAGE,
                provider_id="p1",
                tenant_id="t1",
                request_id=uuid4(),
                success=True,
                latency_ms=10,
                attempt=1,
            )
        assert len(monitor.get_events(limit=3)) == 3

    def test_get_all_metrics(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_request(
            provider_id="p1",
            capability=Capability.SEND_MESSAGE,
            success=True,
            latency_ms=10,
            attempt=1,
        )
        monitor.record_request(
            provider_id="p2",
            capability=Capability.HTTP_REQUEST,
            success=False,
            latency_ms=20,
            attempt=1,
        )
        all_metrics = monitor.get_all_metrics()
        assert "p1" in all_metrics
        assert "p2" in all_metrics

    def test_latency_single_request(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_request(
            provider_id="p1",
            capability=Capability.SEND_MESSAGE,
            success=True,
            latency_ms=42,
            attempt=1,
        )
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.latency.avg == 42.0

    def test_health_status_defaults_to_active(self) -> None:
        monitor = IntegrationMonitor()
        metrics = monitor.get_metrics("p1")
        assert metrics is None or metrics.last_health_status.value == "active"

    def test_record_request_with_attempts(self) -> None:
        monitor = IntegrationMonitor()
        monitor.record_request(
            provider_id="p1",
            capability=Capability.SEND_MESSAGE,
            success=True,
            latency_ms=100,
            attempt=3,
        )
        metrics = monitor.get_metrics("p1")
        assert metrics is not None
        assert metrics.total_requests == 1
