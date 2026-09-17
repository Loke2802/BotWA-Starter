"""Real PostgreSQL receipt locks and outbox claims, with fake delivery only."""

import asyncio
import os
import runpy
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.channel.messaging import ChannelMessageHandler
from app.domain.channel.contracts import InboundChannelMessage, OutboundChannelMessage
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.infrastructure.whatsapp.fake_client import FakeWhatsAppCloudApiClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.test_luri_stabilization import settings
from tests.test_whatsapp_live_processor_repository import cipher, configuration, parsed

URL = os.getenv("BOTWA_TRANSPORT_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Explicit isolated PostgreSQL URL required"
)


def seed(session: Session):  # type: ignore[no-untyped-def]
    cfg = configuration(cipher())
    session.add(
        OrganizationModel(
            id=cfg.organization_id, name="Transport test", slug=str(cfg.organization_id)
        )
    )
    session.flush()
    session.add(
        UserModel(
            id=cfg.created_by_user_id,
            organization_id=cfg.organization_id,
            email=f"{cfg.id}@example.test",
            role="owner",
            status="active",
            password_hash="not-a-login",
        )
    )
    session.flush()
    session.add(
        BotModel(
            id=cfg.bot_id,
            organization_id=cfg.organization_id,
            name="Test",
            slug=str(cfg.bot_id),
            status="active",
        )
    )
    session.flush()
    # Each test channel must have a unique phone number.
    cfg.phone_number_id = str(int(cfg.id) % (10**14))
    session.add(cfg)
    session.commit()
    return cfg


def test_two_processes_claim_one_delivery() -> None:
    assert URL
    engine = create_engine(URL)
    with Session(engine) as db:
        cfg = seed(db)
        attempt = OutboundMessageAttemptModel(
            id=uuid4(),
            organization_id=cfg.organization_id,
            bot_id=cfg.bot_id,
            channel_configuration_id=cfg.id,
            external_recipient_hash="test",
            external_recipient_ciphertext=cipher().encrypt("12025550148"),
            message_ciphertext=cipher().encrypt("Test only"),
            status="pending",
            attempt_count=0,
        )
        db.add(attempt)
        db.commit()
        attempt_id = attempt.id
    barrier = Barrier(2)
    calls = []
    lock = Lock()

    class Client(FakeWhatsAppCloudApiClient):
        async def send_text_message(self, **kwargs):  # type: ignore[no-untyped-def]
            with lock:
                calls.append(1)
            await asyncio.sleep(0.2)
            return await super().send_text_message(**kwargs)

    def deliver(_: int) -> bool:
        with Session(engine) as db:
            processor = get_whatsapp_live_message_processor(
                db, cipher(), Client(), settings()
            )
            barrier.wait(timeout=10)
            return asyncio.run(processor.retry_attempt(attempt_id))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(deliver, [1, 2]))
        assert sorted(outcomes) == [False, True] and calls == [1]
        with Session(engine) as db:
            saved = db.get(OutboundMessageAttemptModel, attempt_id)
            assert saved is not None and saved.status == "sent"
    finally:
        engine.dispose()


def test_duplicate_inbound_executes_business_once() -> None:
    assert URL
    engine = create_engine(URL)
    with Session(engine) as db:
        cfg = seed(db)
        webhook, phone = cfg.public_webhook_id, cfg.phone_number_id
    calls = []
    lock = Lock()
    barrier = Barrier(2)

    class Handler(ChannelMessageHandler):
        def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage:
            with lock:
                calls.append(1)
            time.sleep(0.1)
            return OutboundChannelMessage(
                channel_type="whatsapp",
                external_recipient_id=message.external_sender_id,
                text="Synthetic reply",
            )

    def process(_: int) -> str:
        with Session(engine) as db:
            processor = get_whatsapp_live_message_processor(
                db, cipher(), FakeWhatsAppCloudApiClient(), settings()
            )
            processor._handler = Handler()
            barrier.wait(timeout=10)
            result = asyncio.run(
                processor.process(
                    parsed(phone, f"audit-{webhook}"),
                    public_webhook_id=webhook,
                    correlation_id=uuid4(),
                )
            )
            return result[0].status

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(process, [1, 2]))
        assert sorted(results) == ["duplicate", "processed"] and calls == [1]
    finally:
        engine.dispose()


def test_migration_preserves_and_quarantines_legacy_pending_delivery() -> None:
    assert URL
    engine = create_engine(URL)
    with Session(engine) as db:
        cfg = seed(db)
        attempt = OutboundMessageAttemptModel(
            id=uuid4(),
            organization_id=cfg.organization_id,
            bot_id=cfg.bot_id,
            channel_configuration_id=cfg.id,
            external_recipient_hash="migration-test",
            external_recipient_ciphertext=cipher().encrypt("12025550148"),
            message_ciphertext=cipher().encrypt("Legacy message for review"),
            status="pending",
            attempt_count=1,
        )
        db.add(attempt)
        db.commit()
        attempt_id, ciphertext = attempt.id, attempt.message_ciphertext
    migration = runpy.run_path(
        "alembic/versions/20260916_0024_transport_and_registration.py"
    )
    try:
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            migration["downgrade"]()
            migration["upgrade"]()
        with Session(engine) as db:
            saved = db.get(OutboundMessageAttemptModel, attempt_id)
            assert saved is not None
            assert saved.status == "failed"
            assert saved.last_error_code == "LEGACY_DELIVERY_REVIEW"
            assert saved.message_ciphertext == ciphertext
    finally:
        engine.dispose()
