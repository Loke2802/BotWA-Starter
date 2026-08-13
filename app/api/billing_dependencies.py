from collections.abc import Generator

from app.application.billing.service import BillingService
from app.infrastructure.billing.composition import (
    build_billing_provider,
    build_billing_service,
)
from app.infrastructure.database import get_session
from app.infrastructure.settings import get_settings

get_billing_provider = build_billing_provider


def get_billing_service() -> Generator[BillingService]:
    settings = get_settings()
    session_generator = get_session()
    session = next(session_generator)
    try:
        yield build_billing_service(session, settings)
    finally:
        session_generator.close()
