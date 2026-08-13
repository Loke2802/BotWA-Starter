import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.domain.billing.contracts import (
    CheckoutCommand,
    CheckoutResult,
    NormalizedWebhook,
    PaymentState,
    ProviderSubscriptionSnapshot,
)
from app.domain.billing.errors import (
    BillingProviderRejected,
    BillingProviderUnavailable,
    BillingWebhookInvalid,
)


class MercadoPagoBillingProvider:
    API_BASE = "https://api.mercadopago.com"

    def __init__(
        self,
        *,
        access_token: str,
        webhook_secret: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        signature_tolerance_seconds: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = access_token
        self.webhook_secret = webhook_secret
        self.signature_tolerance_seconds = signature_tolerance_seconds
        self.client = client or httpx.Client(
            base_url=self.API_BASE,
            timeout=httpx.Timeout(
                read_timeout_seconds, connect=connect_timeout_seconds
            ),
        )

    def create_checkout(self, command: CheckoutCommand) -> CheckoutResult:
        data = self._request(
            "POST",
            "/preapproval",
            idempotency_key=command.idempotency_key,
            json_data={
                "preapproval_plan_id": command.provider_price_id,
                "payer_email": command.payer_email,
                "external_reference": command.external_reference,
                "back_url": command.success_url,
                "status": "pending",
            },
        )
        checkout_url = data.get("init_point")
        if not isinstance(checkout_url, str) or not checkout_url.startswith("https://"):
            raise BillingProviderRejected("provider omitted hosted checkout URL")
        provider_id = data.get("id")
        return CheckoutResult(
            checkout_url=checkout_url,
            provider_subscription_id=str(provider_id) if provider_id else None,
            provider_status=str(data.get("status", "pending")),
        )

    def request_plan_change(
        self,
        provider_subscription_id: str,
        provider_price_id: str,
        *,
        unit_amount_minor: int,
        currency: str,
        current_interval: str,
        target_interval: str,
        idempotency_key: str,
    ) -> ProviderSubscriptionSnapshot:
        if current_interval != target_interval:
            raise BillingProviderRejected(
                "billing interval changes require a new provider subscription"
            )
        transaction_amount = f"{unit_amount_minor // 100}.{unit_amount_minor % 100:02d}"
        data = self._request(
            "PUT",
            f"/preapproval/{provider_subscription_id}",
            idempotency_key=idempotency_key,
            json_data={
                "auto_recurring": {
                    "transaction_amount": transaction_amount,
                    "currency_id": currency,
                }
            },
        )
        return self._snapshot(data)

    def request_cancellation(
        self,
        provider_subscription_id: str,
        *,
        idempotency_key: str,
    ) -> ProviderSubscriptionSnapshot:
        data = self._request(
            "PUT",
            f"/preapproval/{provider_subscription_id}",
            idempotency_key=idempotency_key,
            json_data={"status": "canceled"},
        )
        return self._snapshot(data)

    def fetch_subscription(
        self, provider_subscription_id: str
    ) -> ProviderSubscriptionSnapshot:
        return self._snapshot(
            self._request("GET", f"/preapproval/{provider_subscription_id}")
        )

    def verify_and_normalize_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        query: dict[str, str],
    ) -> NormalizedWebhook:
        signature = headers.get("x-signature", "")
        request_id = headers.get("x-request-id", "")
        data_id = query.get("data.id", "")
        parts = dict(part.split("=", 1) for part in signature.split(",") if "=" in part)
        timestamp = parts.get("ts", "")
        received = parts.get("v1", "")
        if not timestamp.isdigit() or not request_id or not data_id or not received:
            raise BillingWebhookInvalid("invalid billing webhook signature headers")
        if abs(int(time.time()) - int(timestamp)) > self.signature_tolerance_seconds:
            raise BillingWebhookInvalid("expired billing webhook signature")
        manifest = f"id:{data_id};request-id:{request_id};ts:{timestamp};"
        expected = hmac.new(
            self.webhook_secret.encode(), manifest.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(received, expected):
            raise BillingWebhookInvalid("invalid billing webhook signature")
        try:
            payload = json.loads(body)
            payload_data = payload["data"]
            if str(payload_data["id"]) != data_id:
                raise BillingWebhookInvalid("billing webhook resource mismatch")
            created_at = _parse_datetime(payload.get("date_created"))
            return NormalizedWebhook(
                event_id=str(payload["id"]),
                event_type=str(payload["type"]),
                provider_subscription_id=data_id,
                provider_created_at=created_at,
            )
        except BillingWebhookInvalid:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BillingWebhookInvalid("invalid billing webhook payload") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        idempotency_key: str | None = None,
        json_data: dict[str, object] | None = None,
    ) -> dict[str, object]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        try:
            response = self.client.request(
                method, path, headers=headers, json=json_data
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BillingProviderUnavailable("billing provider unavailable") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise BillingProviderUnavailable(
                    "billing provider unavailable"
                ) from exc
            raise BillingProviderRejected("billing provider rejected request") from exc
        except (ValueError, TypeError) as exc:
            raise BillingProviderRejected("invalid billing provider response") from exc
        if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
            raise BillingProviderRejected("invalid billing provider response")
        return {str(key): value for key, value in data.items()}

    @staticmethod
    def _snapshot(data: dict[str, object]) -> ProviderSubscriptionSnapshot:
        provider_id = data.get("id")
        reference = data.get("external_reference")
        status = data.get("status")
        if not provider_id or not reference or not status:
            raise BillingProviderRejected("incomplete billing provider response")
        auto_recurring = data.get("auto_recurring")
        recurring = auto_recurring if isinstance(auto_recurring, dict) else {}
        provider_price_id = data.get("preapproval_plan_id")
        provider_amount_minor = _minor_units(recurring.get("transaction_amount"))
        provider_currency = recurring.get("currency_id")
        payment_state: PaymentState = (
            "paid"
            if status == "authorized"
            else "pending" if status == "pending" else "failed"
        )
        sequence = data.get("version")
        return ProviderSubscriptionSnapshot(
            provider_subscription_id=str(provider_id),
            external_reference=str(reference),
            status=str(status),
            current_period_start=_parse_datetime(recurring.get("start_date")),
            current_period_end=_parse_datetime(data.get("next_payment_date")),
            payment_state=payment_state,
            provider_sequence=int(sequence) if isinstance(sequence, int) else None,
            provider_price_id=str(provider_price_id) if provider_price_id else None,
            provider_amount_minor=provider_amount_minor,
            provider_currency=(
                str(provider_currency) if provider_currency is not None else None
            ),
        )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _minor_units(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    minor = amount * 100
    if amount < 0 or minor != minor.to_integral_value():
        return None
    return int(minor)
