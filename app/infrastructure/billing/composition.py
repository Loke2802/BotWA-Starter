from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.application.billing.metrics import billing_metrics
from app.application.billing.service import BillingService
from app.application.plans.service import InternalPlanAssignmentService
from app.domain.billing.contracts import BillingProvider
from app.domain.billing.errors import BillingNotConfigured
from app.domain.billing.ports import BillingProviderPort
from app.infrastructure.billing.fake import FakeBillingProvider
from app.infrastructure.billing.mercado_pago import MercadoPagoBillingProvider
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import Settings

BILLING_PROVIDER_ADAPTER: TypeAdapter[BillingProvider] = TypeAdapter(BillingProvider)


def build_billing_provider(settings: Settings | None = None) -> BillingProviderPort:
    if settings is None:
        from app.infrastructure.settings import get_settings

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


def build_billing_service(session: Session, settings: Settings) -> BillingService:
    plan_repository = SqlAlchemyPlanRepository(session)
    return BillingService(
        BillingRepository(session),
        plan_repository,
        InternalPlanAssignmentService(plan_repository),
        build_billing_provider(settings),
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
        provider_change_lead_seconds=settings.billing_provider_change_lead_seconds,
        metrics=billing_metrics,
    )
