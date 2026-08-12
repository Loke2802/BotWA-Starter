from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

BillingProvider = Literal["mercado_pago", "fake"]
BillingAccountStatus = Literal["active", "inactive"]
BillingPriceStatus = Literal["active", "retired"]
BillingInterval = Literal["monthly", "annual"]
SubscriptionStatus = Literal[
    "pending", "active", "past_due", "suspended", "canceled", "expired"
]
PaymentState = Literal["unknown", "pending", "paid", "failed"]
ProviderEventStatus = Literal["received", "processed", "ignored", "failed"]
BillingFreshness = Literal["fresh", "stale", "unknown"]


class BillingAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    organization_id: UUID
    provider: BillingProvider
    provider_customer_id: str | None
    status: BillingAccountStatus
    version: Annotated[int, Field(gt=0)]
    created_at: datetime
    updated_at: datetime


class BillingPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    plan_definition_id: UUID
    plan_code: str
    provider: BillingProvider
    provider_price_id: str
    amount_minor: Annotated[int, Field(ge=0)]
    currency: str
    interval: BillingInterval
    status: BillingPriceStatus

    @field_validator("currency")
    @classmethod
    def currency_is_iso_shape(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return normalized


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    organization_id: UUID
    billing_account_id: UUID
    billing_price_id: UUID
    provider: BillingProvider
    provider_subscription_id: str | None
    status: SubscriptionStatus
    provider_status: str | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    grace_until: datetime | None
    pending_billing_price_id: UUID | None
    scheduled_change_at: datetime | None
    payment_state: PaymentState
    provider_sequence: int | None
    last_synced_at: datetime | None
    version: Annotated[int, Field(gt=0)]
    created_at: datetime
    updated_at: datetime


class ProviderSubscriptionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_subscription_id: str
    external_reference: str
    status: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    payment_state: PaymentState = "unknown"
    provider_sequence: int | None = None
    provider_price_id: str | None = None
    provider_amount_minor: Annotated[int, Field(ge=0)] | None = None
    provider_currency: str | None = None

    @field_validator("provider_currency")
    @classmethod
    def provider_currency_is_iso_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("provider_currency must be a three-letter ISO code")
        return normalized


class CheckoutCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_reference: str
    provider_price_id: str
    payer_email: str
    success_url: str
    cancel_url: str
    idempotency_key: str


class CheckoutResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checkout_url: str
    provider_subscription_id: str | None = None
    provider_customer_id: str | None = None
    provider_status: str = "pending"


class NormalizedWebhook(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: str
    provider_subscription_id: str | None
    provider_created_at: datetime | None = None


class BillingStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    billing_enabled: bool
    status: SubscriptionStatus | Literal["not_configured", "disabled"]
    plan_code: str
    interval: BillingInterval | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    payment_state: PaymentState = "unknown"
    pending_plan_code: str | None = None
    scheduled_change_at: datetime | None = None
    last_synced_at: datetime | None = None
    freshness: BillingFreshness = "unknown"
    version: int | None = None


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    billing_price_id: UUID


class CheckoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    checkout_url: str
    subscription_id: UUID


class ChangePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    billing_price_id: UUID
    expected_version: Annotated[int, Field(gt=0)]


class CancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: Annotated[int, Field(gt=0)]
    cancel_at_period_end: Literal[True] = True


class ProviderEventReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    duplicate: bool
    status: ProviderEventStatus
