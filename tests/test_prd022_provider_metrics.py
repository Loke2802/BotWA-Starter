import httpx
import pytest
from app.application.integration_management.providers import (
    IntegrationProviderResponseError,
    IntegrationProviderUnreachableError,
)
from app.application.whatsapp_live.client import WhatsAppCloudApiError
from app.domain.billing.contracts import CheckoutCommand
from app.domain.billing.errors import BillingProviderUnavailable
from app.infrastructure.billing.mercado_pago import MercadoPagoBillingProvider
from app.infrastructure.integrations.google_calendar import GoogleCalendarAdapter
from app.infrastructure.whatsapp.meta_client import MetaWhatsAppCloudApiClient
from app.observability.metrics import ObservabilityMetrics, bind_metrics, clear_metrics
from prometheus_client import generate_latest


def _google(transport: httpx.BaseTransport) -> GoogleCalendarAdapter:
    return GoogleCalendarAdapter(
        client_id="client",
        client_secret="secret",
        redirect_uri="https://app.example.test/oauth/callback",
        timeout_seconds=1,
        transport=transport,
    )


async def test_meta_provider_metrics_cover_success_timeout_and_latency() -> None:
    metrics = ObservabilityMetrics()
    token = bind_metrics(metrics)

    async def success(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={"messages": [{"id": "wamid.safe"}]},
        )

    async def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private provider detail", request=request)

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(success)) as http:
            client = MetaWhatsAppCloudApiClient(
                api_version="v22.0", timeout_seconds=1, http_client=http
            )
            await client.send_text_message(
                phone_number_id="12345",
                access_token="secret-token",
                recipient_id="51999999999",
                text="private message body",
            )
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
            client = MetaWhatsAppCloudApiClient(
                api_version="v22.0", timeout_seconds=1, http_client=http
            )
            with pytest.raises(WhatsAppCloudApiError):
                await client.send_text_message(
                    phone_number_id="12345",
                    access_token="secret-token",
                    recipient_id="51999999999",
                    text="private message body",
                )
    finally:
        clear_metrics(token)

    body = generate_latest(metrics.registry).decode()
    assert 'provider="meta",result="success"' in body
    assert 'provider="meta",result="timeout"' in body
    assert "botwa_provider_request_duration_seconds_count" in body
    assert "secret-token" not in body
    assert "private message body" not in body


def test_google_provider_metrics_cover_success_network_and_invalid_response() -> None:
    metrics = ObservabilityMetrics()
    token = bind_metrics(metrics)
    try:
        successful = _google(
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    request=request,
                    json={"access_token": "ephemeral", "refresh_token": "rotated"},
                )
            )
        )
        successful.exchange_authorization_code("private-code")

        def network_failure(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private network detail", request=request)

        with pytest.raises(IntegrationProviderUnreachableError):
            _google(httpx.MockTransport(network_failure)).exchange_authorization_code(
                "private-code"
            )
        with pytest.raises(IntegrationProviderResponseError):
            _google(
                httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        request=request,
                        content=b"not-json-private",
                    )
                )
            ).exchange_authorization_code("private-code")
    finally:
        clear_metrics(token)

    body = generate_latest(metrics.registry).decode()
    assert 'provider="google_calendar",result="success"' in body
    assert 'provider="google_calendar",result="network_error"' in body
    assert 'provider="google_calendar",result="invalid_response"' in body
    assert "private-code" not in body
    assert "not-json-private" not in body


def test_mercado_pago_provider_failure_and_real_retry_labels_are_bounded() -> None:
    metrics = ObservabilityMetrics()
    token = bind_metrics(metrics)

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request, text="private provider error")

    http = httpx.Client(
        base_url="https://api.mercadopago.com",
        transport=httpx.MockTransport(unavailable),
    )
    provider = MercadoPagoBillingProvider(
        access_token="secret-access-token",
        webhook_secret="secret-webhook",
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        signature_tolerance_seconds=300,
        client=http,
    )
    try:
        with pytest.raises(BillingProviderUnavailable):
            provider.create_checkout(
                CheckoutCommand(
                    external_reference="internal-reference",
                    provider_price_id="provider-price",
                    payer_email="private@example.test",
                    success_url="https://app.example.test/success",
                    cancel_url="https://app.example.test/cancel",
                    idempotency_key="private-idempotency-key",
                )
            )
        metrics.record_provider_retry("meta", "send_message", "scheduled")
        metrics.record_provider_retry("meta", "send_message", "exhausted")
    finally:
        http.close()
        clear_metrics(token)

    body = generate_latest(metrics.registry).decode()
    assert 'provider="mercado_pago",result="provider_error"' in body
    assert 'provider="meta",result="scheduled"' in body
    assert 'provider="meta",result="exhausted"' in body
    assert "private@example.test" not in body
    assert "private-idempotency-key" not in body
    assert "secret-access-token" not in body
