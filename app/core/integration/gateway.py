import asyncio
import random
import time
from typing import Any

from app.core.integration.circuit_breaker import CircuitBreaker
from app.core.integration.monitor import IntegrationMonitor
from app.core.integration.provider_client import ProviderClient
from app.core.integration.provider_resolver import ProviderResolver
from app.core.integration.rate_limiter import RateLimiter
from app.domain.integration.contracts import (
    IntegrationError,
    IntegrationRequest,
    IntegrationResult,
    ProviderContext,
    ValidatedIntegrationRequest,
)

NON_RETRYABLE_CODES = frozenset(
    {
        "AUTH_FAILED",
        "WHATSAPP_API_ERROR",
        "HTTP_ERROR",
        "NOT_IMPLEMENTED",
        "UNEXPECTED_ERROR",
    }
)


class IntegrationGateway:
    def __init__(
        self,
        resolver: ProviderResolver | None = None,
        clients: dict[str, ProviderClient] | None = None,
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
        rate_limiter: RateLimiter | None = None,
        monitor: IntegrationMonitor | None = None,
    ) -> None:
        self._resolver = resolver
        self._clients = clients or {}
        self._circuit_breakers = circuit_breakers or {}
        self._rate_limiter = rate_limiter
        self._monitor = monitor

    def validate(
        self, request: IntegrationRequest[Any]
    ) -> ValidatedIntegrationRequest[Any]:
        errors: list[str] = []

        if not request.request_id:
            errors.append("request_id is required")
        if not request.capability:
            errors.append("capability is required")
        if not request.tenant_id:
            errors.append("tenant_id is required")
        if request.payload is None:
            errors.append("payload is required")

        if errors:
            raise ValueError(f"Invalid integration request: {'; '.join(errors)}")

        return ValidatedIntegrationRequest[Any](
            request_id=request.request_id,
            capability=request.capability,
            tenant_id=request.tenant_id,
            payload=request.payload,
            metadata=request.metadata,
            created_at=request.created_at,
        )

    def _get_client(self, provider_id: str) -> ProviderClient:
        client = self._clients.get(provider_id)
        if client is None:
            msg = f"No ProviderClient registered for provider_id: '{provider_id}'"
            raise ValueError(msg)
        return client

    def _is_retryable(self, result: IntegrationResult) -> bool:
        if result.success:
            return False
        code = result.error.code if result.error else ""
        if code in NON_RETRYABLE_CODES:
            status_code = None
            if result.error and result.error.details:
                status_code = result.error.details.get("status_code")
            if isinstance(status_code, int) and 400 <= status_code < 500:
                if status_code != 429:
                    return False
                return False
            if code in ("NOT_IMPLEMENTED", "UNEXPECTED_ERROR", "AUTH_FAILED"):
                return False
        return True

    @staticmethod
    def _compute_delay(base_delay: float, attempt: int) -> float:
        exp: float = base_delay * (2 ** (attempt - 1))
        jitter: float = random.uniform(0, 0.1 * exp)
        return exp + jitter

    def _get_config_or(
        self,
        context: ProviderContext | None,
        attr: str,
        default: int | float,
    ) -> int | float:
        if context and context.config:
            return getattr(context.config, attr, default)
        return default

    async def execute(
        self, request: ValidatedIntegrationRequest[Any]
    ) -> IntegrationResult:
        if self._resolver is None:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="CONFIG_ERROR",
                    message="ProviderResolver not configured",
                ),
            )

        context: ProviderContext | None = None
        try:
            context = self._resolver.resolve(request)
        except ValueError as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="RESOLUTION_ERROR",
                    message=str(exc),
                ),
            )

        provider_id = context.provider.provider_id

        try:
            client = self._get_client(provider_id)
        except ValueError as exc:
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="CLIENT_ERROR",
                    message=str(exc),
                ),
            )

        cb = self._circuit_breakers.get(provider_id)
        if cb is not None and not cb.allow_request():
            if self._monitor is not None:
                self._monitor.record_circuit_breaker_trip(provider_id)
            return IntegrationResult(
                request_id=request.request_id,
                capability=request.capability,
                success=False,
                error=IntegrationError(
                    code="CIRCUIT_OPEN",
                    message=(
                        f"Circuit breaker is OPEN for provider " f"'{provider_id}'"
                    ),
                ),
                circuit_breaker_open=True,
            )

        if self._rate_limiter is not None:
            rate_key = provider_id
            rate_config = self._get_config_or(context, "rate_limit_max_per_second", 80)
            bucket_capacity = self._get_config_or(context, "rate_limit_bucket_size", 80)
            self._rate_limiter.get_or_create(
                rate_key,
                capacity=float(bucket_capacity),
                refill_rate=float(rate_config),
            )
            if not self._rate_limiter.acquire(rate_key):
                if self._monitor is not None:
                    self._monitor.record_rate_limit_hit(provider_id)
                return IntegrationResult(
                    request_id=request.request_id,
                    capability=request.capability,
                    success=False,
                    error=IntegrationError(
                        code="RATE_LIMITED",
                        message=f"Rate limit exceeded for provider '{provider_id}'",
                    ),
                    rate_limited=True,
                )

        config = context.config
        max_attempts = config.retry_max_attempts if config else 3
        base_delay = config.retry_base_delay if config else 1.0
        timeout_sec = config.timeout_seconds if config else 30

        start_time = time.monotonic()

        for attempt in range(1, max_attempts + 1):
            try:
                result = await asyncio.wait_for(
                    client.execute(context, request),
                    timeout=timeout_sec,
                )
            except TimeoutError:
                latency = int((time.monotonic() - start_time) * 1000)
                if attempt >= max_attempts:
                    final = IntegrationResult(
                        request_id=request.request_id,
                        capability=request.capability,
                        success=False,
                        error=IntegrationError(
                            code="TIMEOUT",
                            message=f"Request timed out after {timeout_sec}s",
                            attempt=attempt,
                        ),
                        attempts=attempt,
                        latency_ms=latency,
                    )
                    self._emit(provider_id, request, final, latency, attempt)
                    if cb is not None:
                        cb.record_failure()
                    return final
                delay = self._compute_delay(base_delay, attempt)
                await asyncio.sleep(delay)
                continue
            except Exception as exc:
                latency = int((time.monotonic() - start_time) * 1000)
                if attempt >= max_attempts:
                    final = IntegrationResult(
                        request_id=request.request_id,
                        capability=request.capability,
                        success=False,
                        error=IntegrationError(
                            code="EXECUTION_ERROR",
                            message=str(exc),
                            attempt=attempt,
                        ),
                        attempts=attempt,
                        latency_ms=latency,
                    )
                    self._emit(provider_id, request, final, latency, attempt)
                    if cb is not None:
                        cb.record_failure()
                    return final
                delay = self._compute_delay(base_delay, attempt)
                await asyncio.sleep(delay)
                continue

            latency = int((time.monotonic() - start_time) * 1000)

            if result.success:
                final = result.model_copy(
                    update={
                        "attempts": attempt,
                        "latency_ms": latency,
                    }
                )
                self._emit(provider_id, request, final, latency, attempt)
                if cb is not None:
                    cb.record_success()
                return final

            if not self._is_retryable(result) or attempt >= max_attempts:
                final = result.model_copy(
                    update={
                        "attempts": attempt,
                        "latency_ms": latency,
                    }
                )
                self._emit(provider_id, request, final, latency, attempt)
                if cb is not None:
                    cb.record_failure()
                return final

            delay = self._compute_delay(base_delay, attempt)
            await asyncio.sleep(delay)

        latency = int((time.monotonic() - start_time) * 1000)
        final = IntegrationResult(
            request_id=request.request_id,
            capability=request.capability,
            success=False,
            error=IntegrationError(
                code="MAX_ATTEMPTS_REACHED",
                message=f"All {max_attempts} attempts failed",
                attempt=max_attempts,
            ),
            attempts=max_attempts,
            latency_ms=latency,
        )
        self._emit(provider_id, request, final, latency, max_attempts)
        if cb is not None:
            cb.record_failure()
        return final

    def _emit(
        self,
        provider_id: str,
        request: ValidatedIntegrationRequest[Any],
        result: IntegrationResult,
        latency: int,
        attempt: int,
    ) -> None:
        if self._monitor is None:
            return
        self._monitor.record_request(
            provider_id=provider_id,
            capability=request.capability,
            success=result.success,
            latency_ms=latency,
            attempt=attempt,
        )
        event_type = "integration.completed" if result.success else "integration.failed"
        self._monitor.create_event(
            event_type=event_type,
            capability=request.capability,
            provider_id=provider_id,
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            success=result.success,
            latency_ms=latency,
            attempt=attempt,
            error_code=result.error.code if result.error else None,
            error_message=result.error.message if result.error else None,
        )
