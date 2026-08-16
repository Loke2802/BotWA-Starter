import base64
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
import structlog
from app.api.dependencies import get_auth_service
from app.application.audit.writer import append_non_user_audit
from app.application.auth.service import AuthInvalidCredentialsError
from app.domain.audit.contracts import AuditEventDraft
from app.infrastructure.logging import configure_logging
from app.infrastructure.settings import Environment, Settings, get_settings
from app.main import create_app
from app.observability.context import (
    correlation_context,
    current_correlation_id,
)
from app.observability.health import DatabaseReadinessProbe, ReadinessResult
from app.observability.metrics import (
    ObservabilityMetrics,
    ProviderObservation,
    bind_metrics,
    clear_metrics,
    safe_metric,
)
from app.security.configuration import (
    SecurityConfigurationError,
    SecurityConfigurationValidator,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

_METRICS_TOKEN = "metrics-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _observability_app(
    monkeypatch: pytest.MonkeyPatch, *, metrics_enabled: bool = True
) -> FastAPI:
    monkeypatch.setenv("BOTWA_USE_DATABASE", "false")
    monkeypatch.setenv("BOTWA_METRICS_ENABLED", str(metrics_enabled).lower())
    monkeypatch.setenv("BOTWA_METRICS_BEARER_TOKEN", _METRICS_TOKEN)
    get_settings.cache_clear()
    return create_app()


def _scrape(client: TestClient) -> str:
    response = client.get(
        "/metrics", headers={"Authorization": f"Bearer {_METRICS_TOKEN}"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    return str(response.text)


def _production_settings(**overrides: object) -> Settings:
    settings = Settings(
        environment=Environment.PRODUCTION,
        build_sha="a" * 40,
        auth_secret_key="auth-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-secret",
        legacy_core_api_enabled=False,
        legacy_whatsapp_enabled=False,
        public_bootstrap_enabled=False,
        allowed_hosts=("api.example.com",),
        rate_limit_hmac_key="r" * 48,
        audit_cursor_signing_key="c" * 48,
        integration_oauth_state_secret="o" * 48,
        contact_identity_hmac_key="contact-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        whatsapp_secret_encryption_key=base64.urlsafe_b64encode(b"w" * 32).decode(),
        openapi_enabled=False,
    )
    normalized = dict(overrides)
    metrics_token = normalized.get("metrics_bearer_token")
    if isinstance(metrics_token, str):
        normalized["metrics_bearer_token"] = SecretStr(metrics_token)
    return settings.model_copy(update=normalized)


def test_correlation_id_is_preserved_generated_and_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _observability_app(monkeypatch)
    supplied = uuid4()
    with TestClient(app, raise_server_exceptions=False) as client:
        preserved = client.get("/version", headers={"X-Correlation-ID": str(supplied)})
        generated = client.get("/version", headers={"X-Correlation-ID": "not-a-uuid"})
    assert preserved.headers["X-Correlation-ID"] == str(supplied)
    assert UUID(generated.headers["X-Correlation-ID"]) != supplied
    assert current_correlation_id() is None


def test_concurrent_requests_keep_correlation_ids_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _observability_app(monkeypatch)
    correlation_ids = [uuid4() for _ in range(12)]

    def request(correlation_id: UUID) -> str:
        with TestClient(app) as client:
            response = client.get(
                "/version",
                headers={"X-Correlation-ID": str(correlation_id)},
            )
            return str(response.headers["X-Correlation-ID"])

    with ThreadPoolExecutor(max_workers=6) as executor:
        observed = list(executor.map(request, correlation_ids))
    assert observed == [str(value) for value in correlation_ids]


def test_metrics_are_protected_and_use_bounded_route_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _observability_app(monkeypatch)
    probe = uuid4()
    with TestClient(app) as client:
        client.get("/version")
        client.get(f"/organizations/{probe}")
        client.get(f"/unknown/{probe}")
        client.get("/health/live")
        assert client.get("/metrics").status_code == 401
        assert (
            client.get(
                "/metrics", headers={"Authorization": "Bearer invalid-token"}
            ).status_code
            == 401
        )
        body = _scrape(client)
    assert 'route="/version"' in body
    assert 'route="/organizations/{organization_id}"' in body
    assert 'route="__unmatched__"' in body
    assert str(probe) not in body
    assert 'route="/health/live"' not in body
    assert 'route="/metrics"' not in body


def test_metrics_disabled_is_indistinguishable_from_missing_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _observability_app(monkeypatch, metrics_enabled=False)
    with TestClient(app) as client:
        response = client.get(
            "/metrics", headers={"Authorization": f"Bearer {_METRICS_TOKEN}"}
        )
    assert response.status_code == 404


def test_each_application_factory_has_an_isolated_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _observability_app(monkeypatch)
    second = _observability_app(monkeypatch)
    assert first.state.observability.metrics.registry is not (
        second.state.observability.metrics.registry
    )
    with TestClient(first) as first_client, TestClient(second) as second_client:
        first_client.get("/version")
        assert 'route="/version"' in _scrape(first_client)
        assert 'route="/version"' not in _scrape(second_client)


def test_telemetry_failure_cannot_break_request_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _observability_app(monkeypatch)

    def broken_metric(*_args: object) -> None:
        raise RuntimeError("collector unavailable")

    monkeypatch.setattr(app.state.observability.metrics, "observe_http", broken_metric)
    with TestClient(app) as client:
        response = client.get("/version")
    assert response.status_code == 200


def test_unhandled_failure_is_safe_correlated_and_logged_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _observability_app(monkeypatch)
    logs: list[dict[str, object]] = []

    class RecordingLogger:
        def error(self, event: str, **fields: object) -> None:
            logs.append(
                {
                    "event": event,
                    "bound_correlation_id": current_correlation_id(),
                    **fields,
                }
            )

        def info(self, event: str, **fields: object) -> None:
            logs.append({"event": event, **fields})

        def warning(self, event: str, **fields: object) -> None:
            logs.append({"event": event, **fields})

    monkeypatch.setattr("app.observability.middleware.logger", RecordingLogger())

    @app.get("/observability-test-failure")
    def fail() -> None:
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/observability-test-failure")
    failures = [entry for entry in logs if entry.get("event") == "http_request_failed"]
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "INTERNAL_SERVER_ERROR"}}
    assert UUID(response.headers["X-Correlation-ID"])
    assert len(failures) == 1
    assert failures[0]["bound_correlation_id"] == UUID(
        response.headers["X-Correlation-ID"]
    )
    assert "sensitive internal detail" not in str(failures)


def test_413_429_and_invalid_host_keep_security_and_bounded_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOTWA_GLOBAL_MAX_BODY_BYTES", "1024")
    monkeypatch.setenv("BOTWA_AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", "1")
    app = _observability_app(monkeypatch)

    class MissingUserAuth:
        def login(self, *, email: str, password: str) -> None:
            del email, password
            raise AuthInvalidCredentialsError("invalid credentials")

    app.dependency_overrides[get_auth_service] = MissingUserAuth
    with TestClient(app, raise_server_exceptions=False) as client:
        oversized = client.post(
            "/webhooks/billing/mercado-pago",
            content=b"x" * 1025,
            headers={"Content-Type": "application/json"},
        )
        invalid_host = client.get("/version", headers={"Host": "evil.invalid"})
        credentials = {"email": "missing@example.invalid", "password": "invalid"}
        client.post("/auth/login", json=credentials)
        limited = client.post("/auth/login", json=credentials)
        body = _scrape(client)
    assert oversized.status_code == 413
    assert invalid_host.status_code == 400
    assert limited.status_code == 429
    assert all(
        "X-Correlation-ID" in response.headers
        for response in (oversized, invalid_host, limited)
    )
    assert 'result="oversized"' in body
    assert 'scope="auth_login"' in body
    assert 'status_code="413"' in body
    assert 'status_code="429"' in body
    assert "missing@example.invalid" not in body


@pytest.mark.parametrize("ready", [True, False])
def test_health_contracts_are_minimal_and_do_not_require_provider_calls(
    monkeypatch: pytest.MonkeyPatch, ready: bool
) -> None:
    app = _observability_app(monkeypatch)

    class StaticProbe:
        def check(self) -> ReadinessResult:
            return ReadinessResult(ready=ready)

        def close(self) -> None:
            return

    monkeypatch.setattr(app.state.observability, "readiness", StaticProbe())
    with TestClient(app) as client:
        live = client.get("/health/live")
        readiness = client.get("/health/ready")
        legacy = client.get("/health")
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert legacy.status_code == 200
    assert legacy.json() == {"status": "ok"}
    assert readiness.status_code == (200 if ready else 503)
    expected = (
        {"status": "ready"}
        if ready
        else {"status": "not_ready", "dependencies": {"database": "unavailable"}}
    )
    assert readiness.json() == expected


def test_readiness_probe_uses_real_select_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    healthy = DatabaseReadinessProbe("sqlite+pysqlite:///:memory:", timeout_seconds=0.5)
    assert healthy.check().ready
    healthy.close()

    failing = DatabaseReadinessProbe("sqlite+pysqlite:///:memory:", timeout_seconds=0.5)

    def unavailable() -> None:
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(failing.engine, "connect", unavailable)
    assert not failing.check().ready
    failing.close()


def test_metric_labels_are_closed_and_provider_observation_is_exactly_once() -> None:
    metrics = ObservabilityMetrics()
    token = bind_metrics(metrics)
    try:
        metrics.record_rate_limit("tenant-id", "blocked")
        metrics.observe_provider("unknown", "raw-url", "boom", 1.0)
        metrics.record_audit("audit_query_requests_total", "query", "secret-token", 0)
        metrics.record_plan("plan_query_requests_total", "query", "user@example.com")
        metrics.record_billing("checkout", "idempotency-key")
        metrics.record_onboarding("start", "+51999999999")
        observation = ProviderObservation("meta", "send_message")
        observation.finish("success")
        observation.finish("timeout")
        safe_metric("missing_callback", "ignored")
    finally:
        clear_metrics(token)
    body = generate_latest(metrics.registry).decode("utf-8")
    assert "tenant-id" not in body
    assert "raw-url" not in body
    assert "secret-token" not in body
    assert "user@example.com" not in body
    assert "idempotency-key" not in body
    assert "+51999999999" not in body
    assert (
        'botwa_provider_requests_total{operation="send_message",provider="meta",'
        'result="success"} 1.0'
    ) in body
    assert 'result="timeout"' not in body


def test_structured_logger_emits_parseable_json_without_raw_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    structlog.get_logger("prd022-test").info(
        "operation_completed",
        operation="safe_test",
        result="success",
    )
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    payload = json.loads(lines[-1])
    assert payload["event"] == "operation_completed"
    assert payload["operation"] == "safe_test"
    serialized = json.dumps(payload)
    assert "email" not in serialized
    assert "phone" not in serialized
    assert "token" not in serialized


def test_request_correlation_flows_into_audit_draft() -> None:
    drafts: list[AuditEventDraft] = []

    class RecordingWriter:
        def append(self, draft: AuditEventDraft) -> None:
            drafts.append(draft)

    correlation_id = uuid4()
    with correlation_context(correlation_id):
        append_non_user_audit(
            RecordingWriter(),
            organization_id=uuid4(),
            actor_type="system",
            action="conversation.reopened",
            resource_type="conversation",
            resource_id=uuid4(),
        )
    assert drafts[0].correlation_id == correlation_id


@pytest.mark.parametrize(
    "token",
    [None, "weak", "auth-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-secret"],
)
def test_production_metrics_require_a_strong_dedicated_token(
    token: str | None,
) -> None:
    with pytest.raises(SecurityConfigurationError, match="metrics_bearer_token"):
        SecurityConfigurationValidator().validate(
            _production_settings(metrics_enabled=True, metrics_bearer_token=token)
        )


def test_production_accepts_a_strong_dedicated_metrics_token() -> None:
    SecurityConfigurationValidator().validate(
        _production_settings(
            metrics_enabled=True,
            metrics_bearer_token=_METRICS_TOKEN,
        )
    )


def test_production_metrics_endpoint_accepts_only_the_dedicated_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production_settings(
        metrics_enabled=True,
        metrics_bearer_token=_METRICS_TOKEN,
        use_database=False,
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.observability.routes.get_settings", lambda: settings)
    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/metrics",
            headers={
                "Authorization": f"Bearer {_METRICS_TOKEN}",
                "Host": "api.example.com",
            },
        )
    assert response.status_code == 200
