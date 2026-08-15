from collections.abc import Generator

import structlog
from fastapi import HTTPException, Request, status

from app.domain.security.contracts import SecurityRateLimitScope
from app.infrastructure.database import get_session
from app.infrastructure.repositories.security_rate_limit_repository import (
    SqlAlchemyRateLimitRepository,
)
from app.infrastructure.settings import Environment, get_settings
from app.observability.metrics import safe_metric
from app.security.rate_limit import InMemoryRateLimitRepository, RateLimitService

_development_repository = InMemoryRateLimitRepository()
logger = structlog.get_logger(__name__)


def reset_development_rate_limits() -> None:
    _development_repository.clear()


def get_rate_limit_service() -> Generator[RateLimitService]:
    settings = get_settings()
    key = settings.rate_limit_hmac_key or settings.auth_secret_key
    if settings.environment != Environment.PRODUCTION:
        yield RateLimitService(_development_repository, hmac_key=key)
        return
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield RateLimitService(
            SqlAlchemyRateLimitRepository(
                session,
                retention_seconds=settings.security_rate_limit_retention_seconds,
                cleanup_batch_size=settings.security_rate_limit_cleanup_batch_size,
            ),
            hmac_key=key,
        )
    finally:
        session_generator.close()


def client_origin(request: Request) -> str:
    settings = get_settings()
    peer = request.client.host if request.client is not None else "unknown"
    if peer not in settings.trusted_proxy_hosts:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",", maxsplit=1)[0].strip() or peer


def enforce_rate_limit(
    *,
    request: Request,
    service: RateLimitService,
    scope: SecurityRateLimitScope,
    subject: str,
) -> None:
    settings = get_settings()
    if scope == "auth_login":
        limit = settings.auth_login_rate_limit_attempts
        window = settings.auth_login_rate_limit_window_seconds
    elif scope == "public_bootstrap":
        limit = settings.public_bootstrap_rate_limit_attempts
        window = settings.public_bootstrap_rate_limit_window_seconds
    else:
        limit = settings.webhook_rate_limit_attempts
        window = settings.webhook_rate_limit_window_seconds
    try:
        decision = service.check(
            scope=scope,
            identity=f"{subject}|{client_origin(request)}",
            limit=limit,
            window_seconds=window,
        )
    except Exception:
        safe_metric("record_rate_limit", scope, "persistence_error")
        raise
    safe_metric(
        "record_rate_limit", scope, "allowed" if decision.allowed else "blocked"
    )
    if not decision.allowed:
        if scope == "whatsapp_webhook":
            safe_metric("record_whatsapp_webhook", "rate_limited")
        logger.warning(
            (
                "authentication_rate_limited"
                if scope == "auth_login"
                else "request_rate_limited"
            ),
            scope=scope,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED"},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
