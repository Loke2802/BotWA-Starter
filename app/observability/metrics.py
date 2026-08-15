from contextvars import ContextVar, Token
from time import perf_counter
from typing import Literal

from prometheus_client import CollectorRegistry, Counter, Histogram

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

Provider = Literal["meta", "google_calendar", "mercado_pago"]
ProviderResult = Literal[
    "success",
    "timeout",
    "network_error",
    "rate_limited",
    "auth_error",
    "provider_error",
    "invalid_response",
    "rejected",
]

_PROVIDER_OPERATIONS = frozenset(
    {
        "send_message",
        "oauth_exchange",
        "refresh_token",
        "calendar_list",
        "free_busy",
        "health_check",
        "create_checkout",
        "plan_change",
        "cancel",
        "fetch_subscription",
    }
)
_PROVIDER_RESULTS = frozenset(
    {
        "success",
        "timeout",
        "network_error",
        "rate_limited",
        "auth_error",
        "provider_error",
        "invalid_response",
        "rejected",
    }
)
_RATE_LIMIT_SCOPES = frozenset(
    {"auth_login", "public_bootstrap", "whatsapp_webhook", "billing_webhook"}
)
_HANDOFF_OPERATIONS = frozenset(
    {
        "request",
        "claim",
        "release",
        "transfer",
        "resolve",
        "return_to_bot",
        "bot_reply_suppressed",
    }
)
_WHATSAPP_WEBHOOK_RESULTS = frozenset(
    {
        "accepted",
        "duplicate",
        "signature_invalid",
        "payload_invalid",
        "oversized",
        "rate_limited",
        "failed",
    }
)
_WHATSAPP_MESSAGE_RESULTS = frozenset(
    {"accepted", "duplicate", "sent", "failed", "ignored", "retry_scheduled"}
)


class ObservabilityMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.http_requests = Counter(
            "botwa_http_server_requests_total",
            "HTTP requests completed by the application.",
            ("method", "route", "status_code"),
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "botwa_http_server_request_duration_seconds",
            "HTTP request duration through response completion.",
            ("method", "route", "status_code"),
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.provider_requests = Counter(
            "botwa_provider_requests_total",
            "Outbound provider calls.",
            ("provider", "operation", "result"),
            registry=self.registry,
        )
        self.provider_duration = Histogram(
            "botwa_provider_request_duration_seconds",
            "Outbound provider call duration.",
            ("provider", "operation", "result"),
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.provider_retries = Counter(
            "botwa_provider_retries_total",
            "Retries scheduled by real provider retry logic.",
            ("provider", "operation", "result"),
            registry=self.registry,
        )
        self.whatsapp_webhooks = Counter(
            "botwa_whatsapp_webhooks_total",
            "WhatsApp webhook outcomes.",
            ("result",),
            registry=self.registry,
        )
        self.whatsapp_messages = Counter(
            "botwa_whatsapp_messages_total",
            "WhatsApp message outcomes.",
            ("direction", "result"),
            registry=self.registry,
        )
        self.authentication_attempts = Counter(
            "botwa_authentication_attempts_total",
            "Security-normalized authentication outcomes.",
            ("result",),
            registry=self.registry,
        )
        self.rate_limit_decisions = Counter(
            "botwa_rate_limit_decisions_total",
            "Rate-limit decisions without subject identity.",
            ("scope", "result"),
            registry=self.registry,
        )
        self.handoff_operations = Counter(
            "botwa_handoff_operations_total",
            "Human handoff operation outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.conversation_operations = Counter(
            "botwa_conversation_operations_total",
            "Conversation operational outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.automation_executions = Counter(
            "botwa_automation_executions_total",
            "Managed automation execution outcomes.",
            ("result",),
            registry=self.registry,
        )
        self.calendar_resolutions = Counter(
            "botwa_business_calendar_resolutions_total",
            "Business calendar resolution outcomes.",
            ("state",),
            registry=self.registry,
        )
        self.audit_append = Counter(
            "botwa_audit_append_attempts_total",
            "Audit append acceptance by the Unit of Work.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.audit_queries = Counter(
            "botwa_audit_query_requests_total",
            "Audit query outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.audit_query_duration = Histogram(
            "botwa_audit_query_duration_seconds",
            "Audit query duration in seconds.",
            ("operation", "result"),
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.analytics_operations = Counter(
            "botwa_analytics_operations_total",
            "Analytics operational outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.analytics_duration = Histogram(
            "botwa_analytics_operation_duration_seconds",
            "Analytics operation duration.",
            ("operation", "result"),
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.dashboard_requests = Counter(
            "botwa_dashboard_requests_total",
            "Dashboard query outcomes.",
            ("endpoint", "result"),
            registry=self.registry,
        )
        self.dashboard_duration = Histogram(
            "botwa_dashboard_request_duration_seconds",
            "Dashboard request duration.",
            ("endpoint", "result"),
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.plan_operations = Counter(
            "botwa_plan_operations_total",
            "Plan query, enforcement and assignment outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.billing_operations = Counter(
            "botwa_billing_operations_total",
            "Billing operational outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )
        self.onboarding_operations = Counter(
            "botwa_onboarding_operations_total",
            "Onboarding operational outcomes.",
            ("operation", "result"),
            registry=self.registry,
        )

    def observe_http(
        self, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        status = str(status_code)
        self.http_requests.labels(method.upper(), route, status).inc()
        self.http_duration.labels(method.upper(), route, status).observe(
            max(0.0, duration_seconds)
        )

    def observe_provider(
        self,
        provider: str,
        operation: str,
        result: str,
        duration_seconds: float,
    ) -> None:
        if provider not in {"meta", "google_calendar", "mercado_pago"}:
            return
        if operation not in _PROVIDER_OPERATIONS or result not in _PROVIDER_RESULTS:
            return
        self.provider_requests.labels(provider, operation, result).inc()
        self.provider_duration.labels(provider, operation, result).observe(
            max(0.0, duration_seconds)
        )

    def record_provider_retry(self, provider: str, operation: str, result: str) -> None:
        if (
            provider == "meta"
            and operation == "send_message"
            and result
            in {
                "scheduled",
                "exhausted",
            }
        ):
            self.provider_retries.labels(provider, operation, result).inc()

    def record_whatsapp_webhook(self, result: str) -> None:
        if result in _WHATSAPP_WEBHOOK_RESULTS:
            self.whatsapp_webhooks.labels(result).inc()

    def record_whatsapp_message(self, direction: str, result: str) -> None:
        if direction in {"inbound", "outbound"} and result in _WHATSAPP_MESSAGE_RESULTS:
            self.whatsapp_messages.labels(direction, result).inc()

    def record_authentication(self, result: str) -> None:
        if result in {"success", "failure"}:
            self.authentication_attempts.labels(result).inc()

    def record_rate_limit(self, scope: str, result: str) -> None:
        if scope in _RATE_LIMIT_SCOPES and result in {
            "allowed",
            "blocked",
            "persistence_error",
        }:
            self.rate_limit_decisions.labels(scope, result).inc()

    def record_handoff(self, operation: str, result: str) -> None:
        if operation in _HANDOFF_OPERATIONS and result in {"success", "failure"}:
            self.handoff_operations.labels(operation, result).inc()

    def record_conversation(self, operation: str, result: str) -> None:
        valid_operation = operation in {
            "create",
            "message_persist",
            "archive",
            "reply",
        }
        if valid_operation and result in {"success", "failure", "rejected"}:
            self.conversation_operations.labels(operation, result).inc()

    def record_automation(self, result: str) -> None:
        if result in {"claimed", "completed", "failed", "skipped"}:
            self.automation_executions.labels(result).inc()

    def record_calendar_resolution(self, state: str) -> None:
        if state in {"open", "closed", "error"}:
            self.calendar_resolutions.labels(state).inc()

    def record_audit(
        self, metric: str, operation: str, result: str, duration_ms: int
    ) -> None:
        append_result = result in {
            "accepted_by_unit_of_work",
            "rejected_by_unit_of_work",
        }
        query_result = result in {"success", "error", "forbidden"}
        if (
            metric == "audit_append_attempts_total"
            and operation == "append"
            and append_result
        ):
            self.audit_append.labels(operation, result).inc()
        elif (
            metric == "audit_query_requests_total"
            and operation == "query"
            and query_result
        ):
            self.audit_queries.labels(operation, result).inc()
        elif (
            metric == "audit_query_duration_seconds"
            and operation == "query"
            and query_result
        ):
            self.audit_query_duration.labels(operation, result).observe(
                max(0.0, duration_ms / 1000.0)
            )

    def record_analytics(
        self, _metric: str, operation: str, result: str, duration_ms: int
    ) -> None:
        if operation not in {"rebuild_day", "query", "csv"}:
            return
        normalized = result if result in {"success", "structural_skip"} else "error"
        self.analytics_operations.labels(operation, normalized).inc()
        self.analytics_duration.labels(operation, normalized).observe(
            max(0.0, duration_ms / 1000.0)
        )

    def record_dashboard(self, endpoint: str, result: str, duration_ms: int) -> None:
        if endpoint != "summary":
            return
        normalized = "success" if result == "success" else "error"
        self.dashboard_requests.labels(endpoint, normalized).inc()
        self.dashboard_duration.labels(endpoint, normalized).observe(
            max(0.0, duration_ms / 1000.0)
        )

    def record_plan(self, metric: str, operation: str, result: str) -> None:
        if (
            metric
            in {
                "plan_enforcement_checks_total",
                "plan_enforcement_denials_total",
                "plan_query_requests_total",
                "plan_assignment_changes_total",
            }
            and operation in {"feature", "capacity", "query", "assign"}
            and result
            in {
                "allowed",
                "denied",
                "success",
            }
        ):
            self.plan_operations.labels(operation, result).inc()

    def record_billing(self, operation: str, result: str) -> None:
        if operation in {
            "checkout",
            "plan_change",
            "cancellation",
            "reconciliation",
            "webhook",
            "due_cancellation",
            "due_downgrade",
        } and result in {
            "created",
            "failed",
            "accepted",
            "provider_confirmed",
            "success",
            "duplicate",
            "received",
            "ignored",
            "processed",
            "signature_invalid",
            "oversized",
            "retryable_failure",
            "skipped",
        }:
            self.billing_operations.labels(operation, result).inc()

    def record_onboarding(self, operation: str, result: str) -> None:
        if operation in {"start", "complete", "readiness"} and result in {
            "noop",
            "created",
            "error",
            "conflict",
            "not_ready",
            "completed",
            "ready",
            "degraded",
        }:
            self.onboarding_operations.labels(operation, result).inc()


_current_metrics: ContextVar[ObservabilityMetrics | None] = ContextVar(
    "botwa_observability_metrics", default=None
)


def bind_metrics(metrics: ObservabilityMetrics) -> Token[ObservabilityMetrics | None]:
    return _current_metrics.set(metrics)


def clear_metrics(token: Token[ObservabilityMetrics | None]) -> None:
    _current_metrics.reset(token)


def current_metrics() -> ObservabilityMetrics | None:
    return _current_metrics.get()


def safe_metric(callback: str, *args: object) -> None:
    metrics = current_metrics()
    if metrics is None:
        return
    try:
        method = getattr(metrics, callback)
        method(*args)
    except Exception:
        return


class ProviderObservation:
    def __init__(self, provider: Provider, operation: str) -> None:
        self.provider = provider
        self.operation = operation
        self.started = perf_counter()
        self.completed = False

    def finish(self, result: ProviderResult) -> None:
        if self.completed:
            return
        self.completed = True
        safe_metric(
            "observe_provider",
            self.provider,
            self.operation,
            result,
            perf_counter() - self.started,
        )
