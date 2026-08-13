import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.application.billing.due_transitions import BillingDueTransitionProcessor
from app.application.billing.service import BillingService
from app.application.plans.service import InternalPlanAssignmentService
from app.domain.audit.contracts import AuditEventDraft
from app.domain.billing.contracts import ProviderSubscriptionSnapshot
from app.infrastructure.billing.fake import FakeBillingProvider
from app.infrastructure.models.billing import (
    BillingAccountModel,
    BillingPriceModel,
    BillingProviderEventModel,
    SubscriptionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("BOTWA_PRD019_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD019_POSTGRES_URL is required for explicit PostgreSQL tests",
)


def _url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _alembic(revision: str) -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), revision)


def _plan_configuration() -> dict[str, object]:
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


def test_prd019_postgresql_schema_is_empty_and_constrained() -> None:
    _alembic("20260812_0020")
    engine = create_engine(_url())
    try:
        inspector = inspect(engine)
        assert {
            "billing_account",
            "billing_price",
            "subscription",
            "billing_provider_event",
        } <= set(inspector.get_table_names())
        assert {"organization_id"} in [
            set(item["column_names"])
            for item in inspector.get_unique_constraints("billing_account")
        ]
        assert {"provider", "provider_price_id"} in [
            set(item["column_names"])
            for item in inspector.get_unique_constraints("billing_price")
        ]
        factory = sessionmaker(bind=engine)
        with factory() as session:
            assert session.scalar(select(BillingPriceModel)) is None
            assert session.scalar(select(SubscriptionModel)) is None
            assert session.scalar(select(BillingProviderEventModel)) is None
    finally:
        engine.dispose()


def test_prd019_postgresql_current_subscription_and_event_dedupe() -> None:
    _alembic("20260812_0020")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as session:
        organization = OrganizationModel(
            id=uuid4(),
            name="PRD019",
            slug=f"prd019-{uuid4().hex[:8]}",
            status="active",
            settings={},
        )
        plan = session.scalar(select(PlanDefinitionModel).limit(1))
        assert plan is not None
        session.add(organization)
        session.flush()
        account = BillingAccountModel(
            organization_id=organization.id,
            provider="fake",
            status="active",
            version=1,
            created_at=now,
            updated_at=now,
        )
        price = BillingPriceModel(
            plan_definition_id=plan.id,
            provider="fake",
            provider_price_id="prd019-price",
            amount_minor=1000,
            currency="PEN",
            interval="monthly",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add_all([account, price])
        session.flush()
        first = SubscriptionModel(
            organization_id=organization.id,
            billing_account_id=account.id,
            billing_price_id=price.id,
            provider="fake",
            status="active",
            payment_state="paid",
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(first)
        session.commit()
        session.add(
            SubscriptionModel(
                organization_id=organization.id,
                billing_account_id=account.id,
                billing_price_id=price.id,
                provider="fake",
                status="pending",
                payment_state="pending",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        receipt = BillingProviderEventModel(
            provider="fake",
            provider_event_id="event-1",
            event_type="subscription",
            status="received",
            received_at=now,
            attempts=1,
            payload_hash="a" * 64,
        )
        session.add(receipt)
        session.commit()
        session.add(
            BillingProviderEventModel(
                provider="fake",
                provider_event_id="event-1",
                event_type="subscription",
                status="received",
                received_at=now,
                attempts=1,
                payload_hash="b" * 64,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_prd019_postgresql_concurrent_webhook_receipt_deduplication() -> None:
    _alembic("20260812_0020")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine)
    event_id = f"concurrent-{uuid4()}"
    barrier = Barrier(2)

    def append_receipt(payload_hash: str) -> str:
        with factory() as session:
            session.add(
                BillingProviderEventModel(
                    provider="fake",
                    provider_event_id=event_id,
                    event_type="subscription",
                    status="received",
                    received_at=datetime.now(UTC),
                    attempts=1,
                    payload_hash=payload_hash,
                )
            )
            barrier.wait(timeout=10)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return "duplicate"
            return "accepted"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(append_receipt, "a" * 64)
        second = executor.submit(append_receipt, "b" * 64)
        results = sorted((first.result(timeout=15), second.result(timeout=15)))
    assert results == ["accepted", "duplicate"]
    with factory() as session:
        assert (
            len(
                session.scalars(
                    select(BillingProviderEventModel).where(
                        BillingProviderEventModel.provider_event_id == event_id
                    )
                ).all()
            )
            == 1
        )
    engine.dispose()


def test_prd019_postgresql_webhook_and_due_processor_transition_once() -> None:
    _alembic("20260812_0020")
    engine = create_engine(_url())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    due = now - timedelta(seconds=1)
    organization_id = uuid4()
    subscription_id = uuid4()
    provider_subscription_id = f"race-{uuid4()}"
    provider = FakeBillingProvider(webhook_secret="race-secret")
    provider.subscriptions[provider_subscription_id] = ProviderSubscriptionSnapshot(
        provider_subscription_id=provider_subscription_id,
        external_reference=str(subscription_id),
        status="canceled",
        current_period_end=due,
        payment_state="failed",
        provider_price_id="race-pro-price",
        provider_amount_minor=2000,
        provider_currency="PEN",
    )
    with factory() as session:
        basic = PlanDefinitionModel(
            plan_code=f"race-basic-{uuid4().hex[:8]}",
            display_name="Race Basic",
            status="active",
            configuration=_plan_configuration(),
            created_at=now,
            updated_at=now,
        )
        pro = PlanDefinitionModel(
            plan_code=f"race-pro-{uuid4().hex[:8]}",
            display_name="Race Pro",
            status="active",
            configuration=_plan_configuration(),
            created_at=now,
            updated_at=now,
        )
        organization = OrganizationModel(
            id=organization_id,
            name="PRD019 Race",
            slug=f"prd019-race-{uuid4().hex[:8]}",
            status="active",
            settings={},
        )
        session.add_all([basic, pro, organization])
        session.flush()
        account = BillingAccountModel(
            organization_id=organization_id,
            provider="fake",
            status="active",
            version=1,
            created_at=now,
            updated_at=now,
        )
        price = BillingPriceModel(
            plan_definition_id=pro.id,
            provider="fake",
            provider_price_id="race-pro-price",
            amount_minor=2000,
            currency="PEN",
            interval="monthly",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add_all([account, price])
        session.flush()
        session.add_all(
            [
                OrganizationPlanAssignmentModel(
                    organization_id=organization_id,
                    plan_definition_id=pro.id,
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
                SubscriptionModel(
                    id=subscription_id,
                    organization_id=organization_id,
                    billing_account_id=account.id,
                    billing_price_id=price.id,
                    provider="fake",
                    provider_subscription_id=provider_subscription_id,
                    status="active",
                    provider_status="canceled",
                    current_period_end=due,
                    cancel_at_period_end=True,
                    scheduled_change_at=due,
                    payment_state="paid",
                    version=2,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()
        fallback_plan_code = basic.plan_code

    class ThreadSafeAuditWriter:
        def __init__(self) -> None:
            self.events: list[AuditEventDraft] = []
            self.lock = Lock()

        def append(self, draft: AuditEventDraft) -> None:
            with self.lock:
                self.events.append(draft)

    writer = ThreadSafeAuditWriter()
    barrier = Barrier(2)

    def service_for(session: Session) -> BillingService:
        plans = SqlAlchemyPlanRepository(session)
        return BillingService(
            BillingRepository(session),
            plans,
            InternalPlanAssignmentService(plans),
            provider,
            session,
            writer,
            enabled=True,
            provider_name="fake",
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
            fallback_plan_code=fallback_plan_code,
            freshness_seconds=900,
        )

    event_body = json.dumps(
        {
            "id": "race-event",
            "type": "subscription_preapproval",
            "data": {"id": provider_subscription_id},
        }
    ).encode()
    signature = hmac.new(b"race-secret", event_body, hashlib.sha256).hexdigest()

    def run_processor() -> None:
        with factory() as session:
            service = service_for(session)
            barrier.wait(timeout=10)
            BillingDueTransitionProcessor(
                service.repository, service, session
            ).process_due(now=now, batch_size=10)

    def run_webhook() -> None:
        with factory() as session:
            service = service_for(session)
            barrier.wait(timeout=10)
            service.process_webhook(event_body, {"x-signature": signature}, {})

    with ThreadPoolExecutor(max_workers=2) as executor:
        processor_future = executor.submit(run_processor)
        webhook_future = executor.submit(run_webhook)
        processor_future.result(timeout=20)
        webhook_future.result(timeout=20)

    with factory() as session:
        subscription = session.get(SubscriptionModel, subscription_id)
        assignment = session.get(OrganizationPlanAssignmentModel, organization_id)
        assert subscription is not None and subscription.status == "canceled"
        assert subscription.scheduled_change_at is None
        assert assignment is not None and assignment.plan_definition_id == basic.id
    assert [event.action for event in writer.events].count("subscription.canceled") == 1
    engine.dispose()


def test_prd019_postgresql_migration_cycle_single_head() -> None:
    os.environ["BOTWA_DATABASE_URL"] = _url()
    get_settings.cache_clear()
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "20260812_0020")
    command.downgrade(configuration, "20260810_0019")
    command.upgrade(configuration, "20260812_0020")
    engine = create_engine(_url())
    try:
        assert {
            "billing_account",
            "billing_price",
            "subscription",
            "billing_provider_event",
        } <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
