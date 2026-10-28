"""Isolated public capability API, disabled by default; no admin endpoints."""

import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.security_dependencies import client_origin, get_rate_limit_service
from app.api.webchat_dependencies import get_webchat_service
from app.application.human_handoff.service import HandoffError
from app.application.webchat.service import WebchatService
from app.domain.plans.errors import PlanError
from app.domain.security.contracts import SecurityRateLimitScope
from app.domain.webchat.contracts import (
    WebchatError,
    WebchatHistory,
    WebchatMessageRequest,
    WebchatSession,
)
from app.infrastructure.settings import Environment, Settings, get_settings
from app.security.rate_limit import RateLimitService
from app.security.secret_cipher import SecretCipherError


def webchat_origins(settings: Settings) -> frozenset[str]:
    origins = frozenset(
        x.strip() for x in settings.webchat_origins.split(",") if x.strip()
    )
    if (
        not origins
        or settings.webchat_organization_id is None
        or settings.webchat_bot_id is None
    ):
        raise ValueError("Webchat requires organization, bot and exact origins")
    for origin in origins:
        parsed = urlsplit(origin)
        local = parsed.hostname in {"localhost", "127.0.0.1"}
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or "*" in origin
            or parsed.query
            or parsed.fragment
            or parsed.path
            or (
                parsed.scheme != "https"
                and not (
                    local
                    and parsed.scheme == "http"
                    and settings.environment != Environment.PRODUCTION
                )
            )
        ):
            raise ValueError("Webchat origins must be exact HTTPS origins")
    return origins


def create_webchat_app(settings: Settings) -> FastAPI:
    origins = webchat_origins(settings)
    public = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    public.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=["POST"],
        allow_headers=["Content-Type", "Authorization"],
        allow_credentials=False,
    )

    @public.exception_handler(WebchatError)
    async def webchat_error(request: Request, exc: WebchatError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @public.exception_handler(PlanError)
    async def plan_error(request: Request, exc: PlanError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Chat unavailable for this organization"}, status_code=409
        )

    @public.exception_handler(SQLAlchemyError)
    @public.exception_handler(SecretCipherError)
    async def storage_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "Chat temporarily unavailable"}, status_code=503)

    @public.middleware("http")
    async def no_store(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def validate(
        request: Request,
        limiter: Annotated[RateLimitService, Depends(get_rate_limit_service)],
    ) -> dict[str, object]:
        origin = request.headers.get("origin", "")
        if origin not in origins:
            raise HTTPException(403, "Origin not allowed")
        operation = request.url.path.rsplit("/", 1)[-1]
        scope: SecurityRateLimitScope = (
            "webchat_session"
            if operation == "sessions"
            else ("webchat_read" if operation == "history" else "webchat_write")
        )
        limit = (
            6 if scope == "webchat_session" else 60 if scope == "webchat_read" else 12
        )
        for identity, budget in [
            ("global", limit * 10),
            (client_origin(request), limit),
        ]:
            decision = limiter.check(
                scope=scope,
                identity=f"webchat:{identity}",
                limit=budget,
                window_seconds=60,
            )
            if not decision.allowed:
                raise HTTPException(
                    429,
                    "Too many requests",
                    headers={
                        "Retry-After": str(decision.retry_after_seconds),
                    },
                )
        if (
            request.headers.get("content-type", "").split(";", 1)[0]
            != "application/json"
        ):
            raise HTTPException(415, "JSON required")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 8192:
                raise HTTPException(413, "Request too large")
        try:
            body: object = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(422, "Invalid request") from exc
        if not isinstance(body, dict):
            raise HTTPException(422, "Invalid request")
        return body

    @public.post("/sessions")
    def create(
        request: Request,
        body: Annotated[dict[str, object], Depends(validate)],
        service: Annotated[WebchatService, Depends(get_webchat_service)],
    ) -> WebchatSession:
        if body:
            raise HTTPException(422, "Invalid request")
        return service.create(request.headers["origin"])

    @public.post("/{operation}")
    def operation(
        operation: Literal["messages", "history", "handoff", "close"],
        request: Request,
        body: Annotated[dict[str, object], Depends(validate)],
        service: Annotated[WebchatService, Depends(get_webchat_service)],
    ) -> WebchatHistory | dict[str, bool]:
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer ") or len(authorization) > 150:
            raise HTTPException(401, "Session required")
        token, origin = authorization[7:], request.headers["origin"]
        if operation == "messages":
            try:
                payload = WebchatMessageRequest.model_validate(body)
            except ValueError as exc:
                raise HTTPException(422, "Invalid message") from exc
            return service.submit(token, origin, payload)
        if body:
            raise HTTPException(422, "Invalid request")
        if operation == "history":
            return service.history(token, origin)
        if operation == "close":
            service.close(token, origin)
            return {"closed": True}
        try:
            return service.request_human(token, origin)
        except (HandoffError, PlanError) as exc:
            raise HTTPException(409, "Human attention is unavailable") from exc

    return public


def install_webchat(app: FastAPI) -> None:
    settings = get_settings()
    if settings.webchat_enabled:
        app.mount("/webchat", create_webchat_app(settings))
