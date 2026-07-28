from app.core.integration.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
)


def current_state(cb: CircuitBreaker) -> CircuitBreakerState:
    return cb.state


class TestCircuitBreaker:
    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allow_request_when_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.allow_request() is True

    def test_opens_after_failure_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_does_not_open_below_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allow_request_returns_false_when_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
        cb.record_failure()
        assert cb.allow_request() is False

    def test_transitions_to_half_open_after_recovery_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb.allow_request()
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_records_success_and_closes_in_half_open(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout=0, success_threshold=1
        )
        cb.record_failure()
        cb.allow_request()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_reopens_on_failure_in_half_open(self) -> None:
        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout=0, success_threshold=1
        )
        cb.record_failure()
        cb.allow_request()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_reset_returns_to_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        cb.reset()
        assert current_state(cb) == CircuitBreakerState.CLOSED

    def test_success_in_closed_resets_failure_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allow_request_tracks_time_for_half_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.allow_request() is False
        import asyncio

        asyncio.run(asyncio.sleep(0.15))
        assert cb.allow_request() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_default_values(self) -> None:
        cb = CircuitBreaker()
        assert cb._failure_threshold == 5
        assert cb._recovery_timeout == 30.0
        assert cb._success_threshold == 1
