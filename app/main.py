from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.analytics_routes import router as analytics_router
from app.api.audit_routes import router as audit_router
from app.api.automation_management_routes import router as automation_management_router
from app.api.billing_routes import router as billing_router
from app.api.billing_routes import webhook_router as billing_webhook_router
from app.api.business_calendar_routes import router as business_calendar_router
from app.api.contacts_routes import router as contacts_router
from app.api.conversation_management_routes import (
    router as conversation_management_router,
)
from app.api.dashboard_routes import router as dashboard_router
from app.api.dependencies import get_integration_health_checker
from app.api.human_handoff_routes import router as human_handoff_router
from app.api.integration_management_routes import (
    oauth_router as integration_oauth_router,
)
from app.api.integration_management_routes import (
    router as integration_management_router,
)
from app.api.knowledge_routes import router as knowledge_management_router
from app.api.onboarding_routes import router as onboarding_router
from app.api.plan_routes import router as plan_router
from app.api.routes import bootstrap_router, legacy_router, router
from app.api.security_dependencies import reset_development_rate_limits
from app.api.whatsapp_configuration_routes import (
    router as whatsapp_configuration_router,
)
from app.api.whatsapp_configuration_routes import (
    webhook_router as configured_whatsapp_webhook_router,
)
from app.api.whatsapp_live_routes import router as whatsapp_live_router
from app.channels.whatsapp.webhook import router as whatsapp_router
from app.domain.plans.errors import (
    PlanAssignmentNotFound,
    PlanError,
    PlanFeatureNotAvailable,
    PlanForbidden,
    PlanLimitReached,
    PlanNotFound,
    PlanVersionConflict,
)
from app.infrastructure.database import engine
from app.infrastructure.logging import configure_logging
from app.infrastructure.settings import get_settings
from app.security.configuration import SecurityConfigurationValidator
from app.security.middleware import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    health_checker = get_integration_health_checker()
    await health_checker.start_periodic_check()
    yield
    await health_checker.stop_periodic_check()
    engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    SecurityConfigurationValidator().validate(settings)
    if settings.environment.value != "production":
        reset_development_rate_limits()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.effective_openapi_enabled else None,
        redoc_url="/redoc" if settings.effective_openapi_enabled else None,
        openapi_url="/openapi.json" if settings.effective_openapi_enabled else None,
    )

    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=settings.global_max_body_bytes,
        path_limits={
            "/webhooks/billing/mercado-pago": settings.billing_webhook_max_body_bytes,
        },
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts_enabled=settings.environment.value == "production"
        and settings.https_enabled,
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    @app.exception_handler(PlanError)
    async def handle_plan_error(_request: Request, exc: PlanError) -> JSONResponse:
        if isinstance(exc, (PlanForbidden, PlanFeatureNotAvailable)):
            code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, (PlanNotFound, PlanAssignmentNotFound)):
            code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, (PlanVersionConflict, PlanLimitReached)):
            code = status.HTTP_409_CONFLICT
        else:
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        detail: dict[str, str] = {"code": exc.safe_code}
        if isinstance(exc, PlanLimitReached):
            detail["limit_key"] = exc.limit_key
        return JSONResponse(status_code=code, content={"detail": detail})

    app.include_router(router)
    if settings.public_bootstrap_enabled:
        app.include_router(bootstrap_router)
    if settings.legacy_core_api_enabled:
        app.include_router(legacy_router)
    app.include_router(analytics_router)
    app.include_router(audit_router)
    app.include_router(billing_router)
    app.include_router(billing_webhook_router)
    app.include_router(conversation_management_router)
    app.include_router(contacts_router)
    app.include_router(dashboard_router)
    app.include_router(human_handoff_router)
    app.include_router(automation_management_router)
    app.include_router(business_calendar_router)
    app.include_router(integration_management_router)
    app.include_router(integration_oauth_router)
    app.include_router(knowledge_management_router)
    app.include_router(onboarding_router)
    app.include_router(plan_router)
    app.include_router(whatsapp_configuration_router)
    app.include_router(configured_whatsapp_webhook_router)
    app.include_router(whatsapp_live_router)
    if settings.legacy_whatsapp_enabled:
        app.include_router(whatsapp_router)
    return app


app = create_app()
