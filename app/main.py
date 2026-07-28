from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependencies import get_integration_health_checker
from app.api.routes import router
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
    app.include_router(whatsapp_router)
    return app


app = create_app()
