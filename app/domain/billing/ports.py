from typing import Protocol

from app.domain.billing.contracts import (
    CheckoutCommand,
    CheckoutResult,
    NormalizedWebhook,
    ProviderSubscriptionSnapshot,
)


class BillingProviderPort(Protocol):
    def create_checkout(self, command: CheckoutCommand) -> CheckoutResult: ...

    def request_plan_change(
        self,
        provider_subscription_id: str,
        provider_price_id: str,
        *,
        idempotency_key: str,
    ) -> ProviderSubscriptionSnapshot: ...

    def request_cancellation(
        self,
        provider_subscription_id: str,
        *,
        idempotency_key: str,
    ) -> ProviderSubscriptionSnapshot: ...

    def fetch_subscription(
        self, provider_subscription_id: str
    ) -> ProviderSubscriptionSnapshot: ...

    def verify_and_normalize_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        query: dict[str, str],
    ) -> NormalizedWebhook: ...
