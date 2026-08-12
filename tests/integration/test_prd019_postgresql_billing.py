import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.infrastructure.models.billing import (
    BillingAccountModel,
    BillingPriceModel,
    BillingProviderEventModel,
    SubscriptionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import PlanDefinitionModel
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

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
