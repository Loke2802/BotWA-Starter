from time import perf_counter

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import (
    bind_correlation_id,
    clear_correlation_id,
    normalized_correlation_id,
)
from app.observability.metrics import (
    ObservabilityMetrics,
    bind_metrics,
    clear_metrics,
)

logger = structlog.get_logger(__name__)
_EXCLUDED_ROUTES = frozenset({"/health", "/health/live", "/health/ready", "/metrics"})


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else "__unmatched__"


def _safe_log(level: str, event: str, **fields: object) -> None:
    try:
        getattr(logger, level)(event, **fields)
    except Exception:
        return


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, *, metrics: ObservabilityMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_header = headers.get(b"x-correlation-id")
        supplied = raw_header.decode("ascii", errors="ignore") if raw_header else None
        correlation_id = normalized_correlation_id(supplied)
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["correlation_id"] = correlation_id
        correlation_token = bind_correlation_id(correlation_id)
        metrics_token = bind_metrics(self.metrics)
        started = perf_counter()
        status_code = 500
        response_started = False

        async def observed_send(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append(
                    (b"x-correlation-id", str(correlation_id).encode("ascii"))
                )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        except Exception:
            duration = perf_counter() - started
            route = _route_template(scope)
            self._observe(scope, route, 500, duration)
            _safe_log(
                "error",
                "http_request_failed",
                method=str(scope.get("method", "UNKNOWN")),
                route=route,
                status_code=500,
                error_code="UNEXPECTED_ERROR",
                duration_ms=max(0, int(duration * 1000)),
            )
            raise
        else:
            duration = perf_counter() - started
            route = _route_template(scope)
            self._observe(scope, route, status_code, duration)
            if route not in _EXCLUDED_ROUTES and status_code < 500:
                _safe_log(
                    "info",
                    "http_request_completed",
                    method=str(scope.get("method", "UNKNOWN")),
                    route=route,
                    status_code=status_code,
                    duration_ms=max(0, int(duration * 1000)),
                )
            elif route not in _EXCLUDED_ROUTES:
                _safe_log(
                    "error",
                    "http_request_failed",
                    method=str(scope.get("method", "UNKNOWN")),
                    route=route,
                    status_code=status_code,
                    error_code="HTTP_SERVER_ERROR",
                    duration_ms=max(0, int(duration * 1000)),
                )
            if not response_started:
                _safe_log(
                    "warning",
                    "http_response_not_started",
                    method=str(scope.get("method", "UNKNOWN")),
                    route=route,
                    error_code="RESPONSE_NOT_STARTED",
                )
        finally:
            clear_metrics(metrics_token)
            clear_correlation_id(correlation_token)

    def _observe(
        self, scope: Scope, route: str, status_code: int, duration: float
    ) -> None:
        if route in _EXCLUDED_ROUTES:
            return
        try:
            self.metrics.observe_http(
                str(scope.get("method", "UNKNOWN")),
                route,
                status_code,
                duration,
            )
        except Exception:
            return
