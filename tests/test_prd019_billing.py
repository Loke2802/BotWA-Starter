import hashlib
import hmac
import json
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from app.api.billing_dependencies import get_billing_service
from app.api.billing_routes import router
from app.api.dependencies import require_authenticated_user
from app.application.billing.service import BillingService
from app.application.plans.service import InternalPlanAssignmentService
from app.domain.audit.contracts import AuditEventDraft
from app.domain.audit.ports import AuditWriter
from app.domain.billing.contracts import (
    ChangePlanRequest,
    CheckoutCommand,
    CheckoutRequest,
    ProviderEventReceipt,
    ProviderSubscriptionSnapshot,
)
from app.domain.billing.errors import (
    BillingDisabled,
    BillingForbidden,
    BillingProviderUnavailable,
    BillingWebhookInvalid,
)
from app.domain.user.contracts import User
from app.infrastructure.billing.fake import FakeBillingProvider
from app.infrastructure.billing.mercado_pago import MercadoPagoBillingProvider
from app.infrastructure.database import Base
from app.infrastructure.models.billing import BillingPriceModel, SubscriptionModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventDraft] = []

    def append(self, draft: AuditEventDraft) -> None:
        self.events.append(draft)


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        yield value
    Base.metadata.drop_all(engine)
    engine.dispose()


def _configuration() -> dict[str, object]:
    return {
        "features": {
            "analytics": True,
            "analytics_export": True,
            "audit": True,
            "integrations": True,
            "automations": True,
            "human_handoff": True,
            "business_calendar": True,
            "knowledge": True,
            "whatsapp_configuration": True,
        },
        "limits": {
            "max_active_bots": {"kind": "unlimited"},
            "max_active_users": {"kind": "unlimited"},
            "max_integrations": {"kind": "unlimited"},
            "max_automations": {"kind": "unlimited"},
            "max_business_calendars": {"kind": "unlimited"},
            "max_whatsapp_configurations": {"kind": "unlimited"},
            "max_knowledge_entries": {"kind": "unlimited"},
        },
    }


def _seed(session: Session) -> tuple[UUID, User, BillingPriceModel, BillingPriceModel]:
    organization_id = uuid4()
    user_id = uuid4()
    basic = PlanDefinitionModel(
        id=uuid4(),
        plan_code="basic",
        display_name="Basic",
        status="active",
        configuration=_configuration(),
        created_at=NOW,
        updated_at=NOW,
    )
    pro = PlanDefinitionModel(
        id=uuid4(),
        plan_code="pro",
        display_name="Pro",
        status="active",
        configuration=_configuration(),
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all(
        [
            OrganizationModel(
                id=organization_id,
                name="Tenant",
                slug=f"tenant-{organization_id.hex[:8]}",
                status="active",
                settings={},
                created_at=NOW,
                updated_at=NOW,
            ),
            basic,
            pro,
        ]
    )
    session.flush()
    session.add(
        UserModel(
            id=user_id,
            organization_id=organization_id,
            email="owner@example.com",
            password_hash="hash",
            role="organization_owner",
            status="active",
            auth_version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        OrganizationPlanAssignmentModel(
            organization_id=organization_id,
            plan_definition_id=basic.id,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    basic_price = BillingPriceModel(
        id=uuid4(),
        plan_definition_id=basic.id,
        provider="fake",
        provider_price_id="price-basic-monthly",
        amount_minor=1000,
        currency="PEN",
        interval="monthly",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    pro_price = BillingPriceModel(
        id=uuid4(),
        plan_definition_id=pro.id,
        provider="fake",
        provider_price_id="price-pro-monthly",
        amount_minor=2000,
        currency="PEN",
        interval="monthly",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([basic_price, pro_price])
    session.commit()
    return (
        organization_id,
        User(
            id=user_id,
            organization_id=organization_id,
            email="owner@example.com",
            role="organization_owner",
        ),
        basic_price,
        pro_price,
    )


def _service(
    session: Session,
    provider: FakeBillingProvider,
    writer: AuditWriter,
    *,
    enabled: bool = True,
    fallback: str = "",
) -> BillingService:
    plans = SqlAlchemyPlanRepository(session)
    return BillingService(
        BillingRepository(session),
        plans,
        InternalPlanAssignmentService(plans),
        provider,
        session,
        writer,
        enabled=enabled,
        provider_name="fake",
        success_url="https://app.example.com/billing/success",
        cancel_url="https://app.example.com/billing/cancel",
        fallback_plan_code=fallback,
        freshness_seconds=900,
    )


def _checkout(
    service: BillingService,
    organization_id: UUID,
    actor: User,
    price: BillingPriceModel,
) -> UUID:
    return service.create_checkout(
        organization_id,
        CheckoutRequest(billing_price_id=price.id),
        actor,
        "checkout-key",
    ).subscription_id


def _signed_event(
    service: BillingService,
    provider_subscription_id: str,
    event_id: str,
    *,
    secret: str = "secret",
) -> ProviderEventReceipt:
    body = json.dumps(
        {
            "id": event_id,
            "type": "subscription_preapproval",
            "data": {"id": provider_subscription_id},
        }
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return service.process_webhook(body, {"x-signature": signature}, {})


def test_disabled_mode_is_read_safe_and_rejects_mutations(session: Session) -> None:
    organization_id, actor, basic, _ = _seed(session)
    service = _service(
        session, FakeBillingProvider(), RecordingAuditWriter(), enabled=False
    )
    status = service.get(organization_id, actor)
    assert status.status == "disabled"
    with pytest.raises(BillingDisabled):
        _checkout(service, organization_id, actor, basic)


def test_checkout_is_hosted_idempotent_and_audited(session: Session) -> None:
    organization_id, actor, basic, _ = _seed(session)
    provider = FakeBillingProvider()
    writer = RecordingAuditWriter()
    service = _service(session, provider, writer)
    first = _checkout(service, organization_id, actor, basic)
    second = _checkout(service, organization_id, actor, basic)
    assert first == second
    assert provider.checkout_calls == 2
    assert [event.action for event in writer.events] == [
        "billing.checkout_created",
        "subscription.created",
    ]
    response = service.get(organization_id, actor).model_dump(mode="json")
    assert "provider_subscription_id" not in response
    assert "amount_minor" not in response


def test_verified_webhook_activates_plan_once_and_is_tenant_bound(
    session: Session,
) -> None:
    organization_id, actor, _, pro = _seed(session)
    provider = FakeBillingProvider(webhook_secret="secret")
    writer = RecordingAuditWriter()
    service = _service(session, provider, writer)
    subscription_id = _checkout(service, organization_id, actor, pro)
    row = session.get(SubscriptionModel, subscription_id)
    assert row is not None and row.provider_subscription_id is not None
    provider.activate(row.provider_subscription_id, sequence=2)
    body = json.dumps(
        {
            "id": "event-1",
            "type": "subscription_preapproval",
            "data": {"id": row.provider_subscription_id},
        }
    ).encode()
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    receipt = service.process_webhook(body, {"x-signature": signature}, {})
    duplicate = service.process_webhook(body, {"x-signature": signature}, {})
    assignment = SqlAlchemyPlanRepository(session).get_assignment(organization_id)
    assert receipt.status == "processed"
    assert duplicate.duplicate is True
    assert (
        assignment is not None
        and assignment.plan_definition_id == pro.plan_definition_id
    )
    assert [event.action for event in writer.events].count(
        "subscription.activated"
    ) == 1


def test_upgrade_is_provider_confirmed_and_cancel_is_period_end_only(
    session: Session,
) -> None:
    organization_id, actor, basic, pro = _seed(session)
    provider = FakeBillingProvider()
    writer = RecordingAuditWriter()
    service = _service(session, provider, writer)
    subscription_id = _checkout(service, organization_id, actor, basic)
    row = session.get(SubscriptionModel, subscription_id)
    assert row is not None and row.provider_subscription_id is not None
    provider.activate(row.provider_subscription_id)
    service.reconcile(
        organization_id,
        actor.model_copy(update={"role": "platform_admin"}),
    )
    status = service.request_plan_change(
        organization_id,
        ChangePlanRequest(billing_price_id=pro.id, expected_version=row.version),
        actor,
    )
    assert status.plan_code == "pro"
    canceled = service.request_cancellation(organization_id, status.version or 0, actor)
    assert canceled.cancel_at_period_end is True
    assert provider.cancellation_calls == 0


def test_terminal_without_fallback_never_assigns_default(session: Session) -> None:
    organization_id, actor, basic, _ = _seed(session)
    provider = FakeBillingProvider()
    service = _service(session, provider, RecordingAuditWriter())
    subscription_id = _checkout(service, organization_id, actor, basic)
    row = session.get(SubscriptionModel, subscription_id)
    assert row is not None and row.provider_subscription_id is not None
    provider.activate(row.provider_subscription_id)
    admin = actor.model_copy(update={"role": "platform_admin"})
    service.reconcile(organization_id, admin)
    row.current_period_end = datetime.now(UTC) - timedelta(seconds=1)
    row.cancel_at_period_end = True
    session.commit()
    service.reconcile(organization_id, admin)
    persisted = session.get(SubscriptionModel, subscription_id)
    assignment = SqlAlchemyPlanRepository(session).get_assignment(organization_id)
    assert persisted is not None
    assert persisted.status == "canceled"
    assert persisted.safe_error_code == "BILLING_FALLBACK_NOT_CONFIGURED"
    assert assignment is not None
    assert assignment.plan_definition_id == basic.plan_definition_id


def test_tenant_isolation_and_rbac_are_fail_closed(session: Session) -> None:
    organization_id, _, _, _ = _seed(session)
    other = User(
        organization_id=uuid4(),
        email="other@example.com",
        role="organization_owner",
    )
    with pytest.raises(BillingForbidden):
        _service(session, FakeBillingProvider(), RecordingAuditWriter()).get(
            organization_id, other
        )
    operator = other.model_copy(
        update={"organization_id": organization_id, "role": "operator"}
    )
    with pytest.raises(BillingForbidden):
        _service(session, FakeBillingProvider(), RecordingAuditWriter()).get(
            organization_id, operator
        )


def test_out_of_order_webhook_is_ignored_without_duplicate_audit(
    session: Session,
) -> None:
    organization_id, actor, _, pro = _seed(session)
    provider = FakeBillingProvider(webhook_secret="secret")
    writer = RecordingAuditWriter()
    service = _service(session, provider, writer)
    subscription_id = _checkout(service, organization_id, actor, pro)
    row = session.get(SubscriptionModel, subscription_id)
    assert row is not None and row.provider_subscription_id is not None
    provider.activate(row.provider_subscription_id, sequence=2)
    _signed_event(service, row.provider_subscription_id, "ordered-event")
    provider.subscriptions[row.provider_subscription_id] = ProviderSubscriptionSnapshot(
        provider_subscription_id=row.provider_subscription_id,
        external_reference=str(row.id),
        status="pending",
        payment_state="pending",
        provider_sequence=1,
        provider_price_id=pro.provider_price_id,
    )
    receipt = _signed_event(service, row.provider_subscription_id, "stale-event")
    assert receipt.status == "ignored"
    assert service.get(organization_id, actor).status == "active"
    assert [event.action for event in writer.events].count(
        "subscription.activated"
    ) == 1


def test_unknown_webhook_binding_is_safely_ignored(session: Session) -> None:
    _seed(session)
    service = _service(
        session,
        FakeBillingProvider(webhook_secret="secret"),
        RecordingAuditWriter(),
    )
    receipt = _signed_event(service, "unknown-subscription", "unknown-event")
    assert receipt.status == "ignored"


def test_provider_outage_preserves_last_known_good(session: Session) -> None:
    organization_id, actor, basic, _ = _seed(session)
    provider = FakeBillingProvider()
    service = _service(session, provider, RecordingAuditWriter())
    subscription_id = _checkout(service, organization_id, actor, basic)
    row = session.get(SubscriptionModel, subscription_id)
    assert row is not None and row.provider_subscription_id is not None
    provider.activate(row.provider_subscription_id)
    admin = actor.model_copy(update={"role": "platform_admin"})
    service.reconcile(organization_id, admin)
    provider.available = False
    with pytest.raises(BillingProviderUnavailable):
        service.reconcile(organization_id, admin)
    assert service.get(organization_id, actor).status == "active"


def test_same_price_change_is_noop(session: Session) -> None:
    organization_id, actor, basic, _ = _seed(session)
    provider = FakeBillingProvider()
    writer = RecordingAuditWriter()
    service = _service(session, provider, writer)
    subscription_id = _checkout(service, organization_id, actor, basic)
    row = session.get(SubscriptionModel, subscription_id)
    assert row is not None and row.provider_subscription_id is not None
    provider.activate(row.provider_subscription_id)
    service.reconcile(
        organization_id, actor.model_copy(update={"role": "platform_admin"})
    )
    before_version = row.version
    before_calls = provider.plan_change_calls
    before_audits = len(writer.events)
    response = service.request_plan_change(
        organization_id,
        ChangePlanRequest(billing_price_id=basic.id, expected_version=before_version),
        actor,
    )
    assert response.version == before_version
    assert provider.plan_change_calls == before_calls
    assert len(writer.events) == before_audits


def test_billing_api_uses_typed_contracts(session: Session) -> None:
    organization_id, actor, _, _ = _seed(session)
    service = _service(session, FakeBillingProvider(), RecordingAuditWriter())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_billing_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = lambda: actor
    response = TestClient(app).get(f"/organizations/{organization_id}/billing")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


def test_mercado_pago_webhook_rejects_bad_signature() -> None:
    provider = MercadoPagoBillingProvider(
        access_token="token",
        webhook_secret="secret",
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        signature_tolerance_seconds=300,
    )
    with pytest.raises(BillingWebhookInvalid):
        provider.verify_and_normalize_webhook(
            b"{}",
            {"x-signature": "ts=1,v1=bad", "x-request-id": "request"},
            {"data.id": "subscription"},
        )


def test_mercado_pago_checkout_maps_only_hosted_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["idempotency"] = request.headers.get("x-idempotency-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "mp-subscription",
                "init_point": "https://www.mercadopago.com/checkout",
                "status": "pending",
            },
        )

    provider = MercadoPagoBillingProvider(
        access_token="token",
        webhook_secret="secret",
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        signature_tolerance_seconds=300,
        client=httpx.Client(
            base_url="https://api.mercadopago.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    result = provider.create_checkout(
        CheckoutCommand(
            external_reference="internal-subscription",
            provider_price_id="provider-plan",
            payer_email="owner@example.com",
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
            idempotency_key="idem",
        )
    )
    assert result.checkout_url.startswith("https://")
    assert captured["authorization"] == "Bearer token"
    assert captured["idempotency"] == "idem"
    body = captured["body"]
    assert isinstance(body, dict)
    assert not {"pan", "cvv", "payment_method"}.intersection(body)


def test_mercado_pago_valid_signature_is_normalized() -> None:
    provider = MercadoPagoBillingProvider(
        access_token="token",
        webhook_secret="secret",
        connect_timeout_seconds=1,
        read_timeout_seconds=1,
        signature_tolerance_seconds=300,
    )
    timestamp = str(int(time.time()))
    manifest = f"id:mp-sub;request-id:req-1;ts:{timestamp};"
    signature = hmac.new(b"secret", manifest.encode(), hashlib.sha256).hexdigest()
    body = json.dumps(
        {
            "id": "event-2",
            "type": "subscription_preapproval",
            "data": {"id": "mp-sub"},
        }
    ).encode()
    normalized = provider.verify_and_normalize_webhook(
        body,
        {
            "x-signature": f"ts={timestamp},v1={signature}",
            "x-request-id": "req-1",
        },
        {"data.id": "mp-sub"},
    )
    assert normalized.event_id == "event-2"
    assert normalized.provider_subscription_id == "mp-sub"


def test_audit_failure_rolls_back_local_checkout(session: Session) -> None:
    organization_id, actor, basic, _ = _seed(session)

    class FailingWriter:
        def append(self, draft: AuditEventDraft) -> None:
            del draft
            raise RuntimeError("audit unavailable")

    provider = FakeBillingProvider()
    service = _service(session, provider, FailingWriter())
    with pytest.raises(RuntimeError):
        _checkout(service, organization_id, actor, basic)
    assert BillingRepository(session).latest_subscription_model(organization_id) is None


def test_migration_declares_expected_revision_and_no_seed() -> None:
    content = (
        __import__("pathlib")
        .Path("alembic/versions/20260812_0020_create_billing_subscriptions.py")
        .read_text(encoding="utf-8")
    )
    assert 'revision = "20260812_0020"' in content
    assert 'down_revision = "20260810_0019"' in content
    assert "INSERT INTO" not in content
    assert content.count("op.create_table(") == 4
