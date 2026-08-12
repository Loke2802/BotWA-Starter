import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from app.domain.billing.contracts import (
    CheckoutCommand,
    CheckoutResult,
    NormalizedWebhook,
    ProviderSubscriptionSnapshot,
)
from app.domain.billing.errors import BillingProviderRejected, BillingWebhookInvalid


class FakeBillingProvider:
    """Deterministic provider for unit and contract tests."""

    def __init__(self, *, webhook_secret: str = "test-secret") -> None:
        self.webhook_secret = webhook_secret
        self.subscriptions: dict[str, ProviderSubscriptionSnapshot] = {}
        self.checkout_calls = 0
        self.plan_change_calls = 0
        self.cancellation_calls = 0
        self.available = True

    def create_checkout(self, command: CheckoutCommand) -> CheckoutResult:
        self._require_available()
        self.checkout_calls += 1
        provider_id = f"fake-sub-{command.external_reference}"
        self.subscriptions[provider_id] = ProviderSubscriptionSnapshot(
            provider_subscription_id=provider_id,
            external_reference=command.external_reference,
            status="pending",
            payment_state="pending",
            provider_price_id=command.provider_price_id,
        )
        return CheckoutResult(
            checkout_url=f"https://checkout.example.invalid/{provider_id}",
            provider_subscription_id=provider_id,
        )

    def request_plan_change(
        self,
        provider_subscription_id: str,
        provider_price_id: str,
        *,
        idempotency_key: str,
    ) -> ProviderSubscriptionSnapshot:
        del idempotency_key
        self._require_available()
        self.plan_change_calls += 1
        current = self.fetch_subscription(provider_subscription_id)
        changed = current.model_copy(update={"provider_price_id": provider_price_id})
        self.subscriptions[provider_subscription_id] = changed
        return changed

    def request_cancellation(
        self,
        provider_subscription_id: str,
        *,
        idempotency_key: str,
    ) -> ProviderSubscriptionSnapshot:
        del idempotency_key
        self._require_available()
        self.cancellation_calls += 1
        current = self.fetch_subscription(provider_subscription_id)
        canceled = current.model_copy(update={"status": "cancelled"})
        self.subscriptions[provider_subscription_id] = canceled
        return canceled

    def fetch_subscription(
        self, provider_subscription_id: str
    ) -> ProviderSubscriptionSnapshot:
        self._require_available()
        try:
            return self.subscriptions[provider_subscription_id]
        except KeyError as exc:
            raise BillingProviderRejected("provider subscription not found") from exc

    def activate(
        self,
        provider_subscription_id: str,
        *,
        period_days: int = 30,
        sequence: int | None = None,
    ) -> None:
        current = self.fetch_subscription(provider_subscription_id)
        now = datetime.now(UTC)
        self.subscriptions[provider_subscription_id] = current.model_copy(
            update={
                "status": "authorized",
                "payment_state": "paid",
                "current_period_start": now,
                "current_period_end": now + timedelta(days=period_days),
                "provider_sequence": sequence,
            }
        )

    def verify_and_normalize_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        query: dict[str, str],
    ) -> NormalizedWebhook:
        del query
        signature = headers.get("x-signature", "")
        expected = hmac.new(
            self.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise BillingWebhookInvalid("invalid billing webhook signature")
        try:
            payload = json.loads(body)
            data = payload["data"]
            return NormalizedWebhook(
                event_id=str(payload["id"]),
                event_type=str(payload["type"]),
                provider_subscription_id=str(data["id"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BillingWebhookInvalid("invalid billing webhook payload") from exc

    def _require_available(self) -> None:
        if not self.available:
            from app.domain.billing.errors import BillingProviderUnavailable

            raise BillingProviderUnavailable("billing provider unavailable")
