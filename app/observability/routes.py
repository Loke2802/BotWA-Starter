import hmac
from contextlib import suppress
from typing import Annotated

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.infrastructure.settings import get_settings
from app.observability.runtime import ObservabilityRuntime

router = APIRouter(tags=["system"])
logger = structlog.get_logger(__name__)


@router.get("/metrics", include_in_schema=False)
def metrics_endpoint(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    configured = settings.metrics_bearer_token
    expected = configured.get_secret_value() if configured is not None else ""
    supplied = ""
    if authorization is not None and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(supplied, expected):
        with suppress(Exception):
            logger.warning(
                "metrics_authentication_failed", error_code="METRICS_UNAUTHORIZED"
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    runtime: ObservabilityRuntime = request.app.state.observability
    return Response(
        content=generate_latest(runtime.metrics.registry),
        media_type=CONTENT_TYPE_LATEST,
    )
