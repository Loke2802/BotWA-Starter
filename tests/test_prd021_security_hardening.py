import base64
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from app.api.dependencies import get_auth_service
from app.api.security_dependencies import get_rate_limit_service
from app.domain.user.contracts import TokenResponse
from app.infrastructure.database import Base
from app.infrastructure.logging import SensitiveQueryParameterFilter
from app.infrastructure.models.security_rate_limit import SecurityRateLimitBucketModel
from app.infrastructure.repositories.security_rate_limit_repository import (
    SqlAlchemyRateLimitRepository,
)
from app.infrastructure.settings import Environment, Settings
from app.main import create_app
from app.security.configuration import (
    SecurityConfigurationError,
    SecurityConfigurationValidator,
)
from app.security.middleware import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.security.rate_limit import InMemoryRateLimitRepository, RateLimitService
from app.security.tokens import AccessTokenService
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def _production_settings(**overrides: object) -> Settings:
    baseline = Settings(
        environment=Environment.PRODUCTION,
        auth_secret_key="auth-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-secret",
        auth_algorithm="HS256",
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
    return baseline.model_copy(update=overrides)


@pytest.mark.parametrize(
    ("override", "control"),
    [
        ({"auth_secret_key": "local-development-secret-change-me"}, "auth_signing_key"),
        ({"legacy_core_api_enabled": True}, "legacy_core_api"),
        ({"legacy_whatsapp_enabled": True}, "legacy_whatsapp"),
        ({"public_bootstrap_enabled": True}, "public_bootstrap"),
        ({"allowed_hosts": ("*",)}, "allowed_hosts"),
        (
            {"cors_origins": ("*",), "cors_allow_credentials": True},
            "cors",
        ),
        ({"rate_limit_hmac_key": "weak"}, "rate_limit_hmac_key"),
        ({"audit_cursor_signing_key": "weak"}, "audit_cursor_signing_key"),
        ({"integration_oauth_state_secret": "weak"}, "oauth_state_signing_key"),
    ],
)
def test_production_security_validator_rejects_unsafe_configuration(
    override: dict[str, object], control: str
) -> None:
    with pytest.raises(SecurityConfigurationError, match=control):
        SecurityConfigurationValidator().validate(_production_settings(**override))


def test_production_security_validator_accepts_explicit_safe_profile() -> None:
    SecurityConfigurationValidator().validate(_production_settings())


def test_openapi_defaults_to_development_only() -> None:
    assert Settings(environment="development").effective_openapi_enabled
    assert Settings(environment="test").effective_openapi_enabled
    assert not Settings(environment="production").effective_openapi_enabled


def test_token_algorithm_is_closed_allowlist() -> None:
    with pytest.raises(ValueError, match="unsupported token algorithm"):
        AccessTokenService("x" * 32, "none", 30)


def test_legacy_routes_are_not_mounted_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        environment="test",
        legacy_core_api_enabled=False,
        legacy_whatsapp_enabled=False,
        public_bootstrap_enabled=False,
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    client = TestClient(create_app())

    assert client.post("/messages", json={}).status_code == 404
    assert client.post("/conversation/message", json={}).status_code == 404
    assert client.post("/webhooks/whatsapp", json={}).status_code == 404
    assert client.post("/organizations", json={}).status_code == 405


def _limited_app() -> FastAPI:
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request) -> PlainTextResponse:
        return PlainTextResponse(str(len(await request.body())))

    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=8)
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=False)
    return app


def test_body_limiter_rejects_declared_and_streamed_oversize() -> None:
    client = TestClient(_limited_app())
    declared = client.post("/echo", content=b"123456789")

    def chunks() -> Iterator[bytes]:
        yield b"12345"
        yield b"67890"

    streamed = client.post("/echo", content=chunks())

    assert declared.status_code == 413
    assert streamed.status_code == 413
    assert streamed.json()["detail"]["code"] == "REQUEST_BODY_TOO_LARGE"


def test_security_headers_are_present_and_hsts_is_explicit() -> None:
    client = TestClient(_limited_app())
    response = client.post("/echo", content=b"ok")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


def test_rate_limiter_persists_only_hmac_key_and_enforces_threshold() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = RateLimitService(
            SqlAlchemyRateLimitRepository(session), hmac_key="k" * 32
        )
        first = service.check(
            scope="auth_login",
            identity="Owner@Example.com|127.0.0.1",
            limit=2,
            window_seconds=60,
        )
        second = service.check(
            scope="auth_login",
            identity="owner@example.com|127.0.0.1",
            limit=2,
            window_seconds=60,
        )
        blocked = service.check(
            scope="auth_login",
            identity="owner@example.com|127.0.0.1",
            limit=2,
            window_seconds=60,
        )
        row = session.scalars(select(SecurityRateLimitBucketModel)).one()

    assert first.allowed and second.allowed
    assert not blocked.allowed and blocked.retry_after_seconds > 0
    assert row.attempt_count == 3
    assert row.key_hash != "owner@example.com|127.0.0.1"
    assert len(row.key_hash) == 64


def test_sqlite_rate_limit_cleanup_preserves_active_and_bounds_batch() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    active_window = now.replace(second=0, microsecond=0)
    expired_keys = {f"{index:064x}" for index in range(5)}
    with Session(engine) as session:
        session.add_all(
            [
                SecurityRateLimitBucketModel(
                    scope="auth_login",
                    key_hash=f"{index:064x}",
                    window_started_at=now - timedelta(days=3, seconds=index),
                    attempt_count=1,
                    blocked_until=None,
                    updated_at=now - timedelta(days=3, seconds=index),
                )
                for index in range(5)
            ]
            + [
                SecurityRateLimitBucketModel(
                    scope="auth_login",
                    key_hash="f" * 64,
                    window_started_at=active_window,
                    attempt_count=1,
                    blocked_until=None,
                    updated_at=now,
                )
            ]
        )
        session.commit()
        SqlAlchemyRateLimitRepository(session, cleanup_batch_size=2).consume(
            scope="auth_login",
            key_hash="e" * 64,
            limit=5,
            window_seconds=60,
        )
        rows = session.scalars(select(SecurityRateLimitBucketModel)).all()

    assert len([row for row in rows if row.key_hash in expired_keys]) == 3
    assert any(row.key_hash == "f" * 64 for row in rows)


def test_login_rate_limit_returns_safe_429_and_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        environment="test",
        auth_login_rate_limit_attempts=1,
        auth_login_rate_limit_window_seconds=60,
    )
    monkeypatch.setattr("app.api.security_dependencies.get_settings", lambda: settings)
    repository = InMemoryRateLimitRepository()
    limiter = RateLimitService(repository, hmac_key="k" * 32)

    class SuccessfulAuth:
        def login(self, email: str, password: str) -> TokenResponse:
            return TokenResponse(access_token="safe-token", expires_in=60)

    app = create_app()
    app.dependency_overrides[get_auth_service] = SuccessfulAuth
    app.dependency_overrides[get_rate_limit_service] = lambda: limiter
    client = TestClient(app)
    payload = {"email": "owner@example.com", "password": "candidate-password"}

    assert client.post("/auth/login", json=payload).status_code == 200
    blocked = client.post("/auth/login", json=payload)

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]
    assert blocked.json()["detail"]["code"] == "RATE_LIMITED"


def test_oauth_code_and_state_are_redacted_from_access_log() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1",
            "GET",
            "/oauth/callback?code=raw-code&state=raw-state&safe=value",
            "1.1",
            200,
        ),
        None,
    )
    SensitiveQueryParameterFilter().filter(record)
    rendered = str(record.args)

    assert "raw-code" not in rendered
    assert "raw-state" not in rendered
    assert rendered.count("%5BREDACTED%5D") == 2
    assert "safe=value" in rendered
