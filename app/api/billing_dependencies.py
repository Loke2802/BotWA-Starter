from collections.abc import Generator

from pydantic import TypeAdapter

from app.application.billing.metrics import billing_metrics
from app.application.billing.service import BillingService
from app.application.plans.service import InternalPlanAssignmentService
from app.domain.billing.contracts import BillingProvider
from app.domain.billing.errors import BillingNotConfigured
from app.domain.billing.ports import BillingProviderPort
from app.infrastructure.billing.fake import FakeBillingProvider
from app.infrastructure.billing.mercado_pago import MercadoPagoBillingProvider
from app.infrastructure.database import get_session
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import get_settings

BILLING_PROVIDER_ADAPTER: TypeAdapter[BillingProvider] = TypeAdapter(BillingProvider)


def get_billing_provider() -> BillingProviderPort:
    settings = get_settings()
    if settings.billing_provider == "fake":
        return FakeBillingProvider(
            webhook_secret=settings.billing_mercado_pago_webhook_secret or "test-secret"
        )
    if settings.billing_provider != "mercado_pago":
        raise BillingNotConfigured("unsupported billing provider")
    return MercadoPagoBillingProvider(
        access_token=settings.billing_mercado_pago_access_token,
        webhook_secret=settings.billing_mercado_pago_webhook_secret,
        connect_timeout_seconds=settings.billing_connect_timeout_seconds,
        read_timeout_seconds=settings.billing_read_timeout_seconds,
        signature_tolerance_seconds=settings.billing_webhook_signature_tolerance_seconds,
    )


def get_billing_service() -> Generator[BillingService]:
    settings = get_settings()
    session_generator = get_session()
    session = next(session_generator)
    try:
        plan_repository = SqlAlchemyPlanRepository(session)
        yield BillingService(
            BillingRepository(session),
            plan_repository,
            InternalPlanAssignmentService(plan_repository),
            get_billing_provider(),
            session,
            SqlAlchemyAuditRepository(session),
            enabled=settings.billing_enabled,
            provider_name=BILLING_PROVIDER_ADAPTER.validate_python(
                settings.billing_provider
            ),
            success_url=settings.billing_success_url,
            cancel_url=settings.billing_cancel_url,
            fallback_plan_code=settings.billing_fallback_plan_code,
            freshness_seconds=settings.billing_freshness_seconds,
            metrics=billing_metrics,
        )
    finally:
        session_generator.close()
