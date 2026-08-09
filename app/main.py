from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.analytics_routes import router as analytics_router
from app.api.automation_management_routes import router as automation_management_router
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
from app.api.routes import router
from app.api.whatsapp_configuration_routes import (
    router as whatsapp_configuration_router,
)
from app.api.whatsapp_configuration_routes import (
    webhook_router as configured_whatsapp_webhook_router,
)
from app.api.whatsapp_live_routes import router as whatsapp_live_router
from app.channels.whatsapp.webhook import router as whatsapp_router
from app.infrastructure.database import engine
from app.infrastructure.logging import configure_logging
from app.infrastructure.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    health_checker = get_integration_health_checker()
    await health_checker.start_periodic_check()
    yield
    await health_checker.stop_periodic_check()
    engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(analytics_router)
    app.include_router(conversation_management_router)
    app.include_router(contacts_router)
    app.include_router(dashboard_router)
    app.include_router(human_handoff_router)
    app.include_router(automation_management_router)
    app.include_router(business_calendar_router)
    app.include_router(integration_management_router)
    app.include_router(integration_oauth_router)
    app.include_router(knowledge_management_router)
    app.include_router(whatsapp_configuration_router)
    app.include_router(configured_whatsapp_webhook_router)
    app.include_router(whatsapp_live_router)
    app.include_router(whatsapp_router)
    return app


app = create_app()
