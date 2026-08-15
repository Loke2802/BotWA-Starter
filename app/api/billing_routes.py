from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.billing_dependencies import get_billing_service
from app.api.dependencies import require_authenticated_user
from app.api.security_dependencies import enforce_rate_limit, get_rate_limit_service
from app.application.billing.service import BillingService
from app.domain.billing.contracts import (
    BillingStatusResponse,
    CancellationRequest,
    ChangePlanRequest,
    CheckoutRequest,
    CheckoutResponse,
    ProviderEventReceipt,
)
from app.domain.billing.errors import (
    BillingDisabled,
    BillingError,
    BillingForbidden,
    BillingNotConfigured,
    BillingPriceNotFound,
    BillingPriceUnavailable,
    BillingProviderRejected,
    BillingProviderUnavailable,
    BillingVersionConflict,
    BillingWebhookInvalid,
    SubscriptionConflict,
    SubscriptionNotFound,
)
from app.domain.user.contracts import User
from app.infrastructure.settings import get_settings
from app.observability.metrics import safe_metric
from app.security.rate_limit import RateLimitService

router = APIRouter(prefix="/organizations/{organization_id}/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/webhooks/billing", tags=["billing-webhooks"])


def raise_billing_error(exc: BillingError) -> NoReturn:
    if isinstance(exc, BillingForbidden):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (BillingPriceNotFound, SubscriptionNotFound)):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        exc,
        (
            BillingVersionConflict,
            SubscriptionConflict,
            BillingPriceUnavailable,
        ),
    ):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, BillingWebhookInvalid):
        code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, (BillingDisabled, BillingNotConfigured)):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, BillingProviderRejected):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, BillingProviderUnavailable):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=code, detail={"code": exc.safe_code}) from exc


@router.get("", response_model=BillingStatusResponse)
def get_billing_status(
    organization_id: UUID,
    service: Annotated[BillingService, Depends(get_billing_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> BillingStatusResponse:
    try:
        return service.get(organization_id, actor)
    except BillingError as exc:
        raise_billing_error(exc)


@router.post("/checkout", response_model=CheckoutResponse, status_code=201)
def create_checkout(
    organization_id: UUID,
    payload: CheckoutRequest,
    service: Annotated[BillingService, Depends(get_billing_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> CheckoutResponse:
    try:
        return service.create_checkout(organization_id, payload, actor, idempotency_key)
    except BillingError as exc:
        raise_billing_error(exc)


@router.post("/change-plan", response_model=BillingStatusResponse)
def change_plan(
    organization_id: UUID,
    payload: ChangePlanRequest,
    service: Annotated[BillingService, Depends(get_billing_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> BillingStatusResponse:
    try:
        return service.request_plan_change(organization_id, payload, actor)
    except BillingError as exc:
        raise_billing_error(exc)


@router.post("/cancel", response_model=BillingStatusResponse)
def cancel_subscription(
    organization_id: UUID,
    payload: CancellationRequest,
    service: Annotated[BillingService, Depends(get_billing_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> BillingStatusResponse:
    try:
        return service.request_cancellation(
            organization_id, payload.expected_version, actor
        )
    except BillingError as exc:
        raise_billing_error(exc)


@router.post("/reconcile", response_model=BillingStatusResponse)
def reconcile_subscription(
    organization_id: UUID,
    service: Annotated[BillingService, Depends(get_billing_service)],
    actor: Annotated[User, Depends(require_authenticated_user)],
) -> BillingStatusResponse:
    try:
        return service.reconcile(organization_id, actor)
    except BillingError as exc:
        raise_billing_error(exc)


@webhook_router.post("/mercado-pago", response_model=ProviderEventReceipt)
async def mercado_pago_webhook(
    request: Request,
    service: Annotated[BillingService, Depends(get_billing_service)],
    rate_limiter: Annotated[RateLimitService, Depends(get_rate_limit_service)],
) -> ProviderEventReceipt:
    enforce_rate_limit(
        request=request,
        service=rate_limiter,
        scope="billing_webhook",
        subject="mercado_pago",
    )
    body = await request.body()
    if len(body) > get_settings().billing_webhook_max_body_bytes:
        safe_metric("record_billing", "webhook", "oversized")
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={"code": "BILLING_WEBHOOK_INVALID"},
        )
    try:
        return service.process_webhook(
            body,
            {key.lower(): value for key, value in request.headers.items()},
            dict(request.query_params),
        )
    except BillingError as exc:
        if isinstance(exc, BillingWebhookInvalid):
            safe_metric("record_billing", "webhook", "signature_invalid")
        raise_billing_error(exc)
