import time
from enum import StrEnum


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._total_failures = 0
        self._total_successes = 0

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def total_failures(self) -> int:
        return self._total_failures

    @property
    def total_successes(self) -> int:
        return self._total_successes

    def allow_request(self) -> bool:
        now = time.monotonic()
        if self._state == CircuitBreakerState.OPEN:
            if now - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitBreakerState.HALF_OPEN
                self._success_count = 0
                return True
            return False
        return True

    def record_success(self) -> None:
        self._total_successes += 1
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitBreakerState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        self._total_failures += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitBreakerState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitBreakerState.OPEN
        elif self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN

    def reset(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
