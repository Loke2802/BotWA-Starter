"""Real PG leases, transactions and idempotency; external providers stay fake."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from app.infrastructure.models.ai_generation import AIJobModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from tests.test_generative_ai import (
    Runtime,
)
from tests.test_generative_ai import (
    test_durable_webhook_generation_outbox_idempotency as check_flow,
)
from tests.test_generative_ai import (
    test_no_checked_out_connection_during_provider as check_connections,
)
from tests.test_generative_ai import (
    test_restart_and_stale_owner_fencing as check_restart,
)
from tests.test_generative_ai import (
    test_unpublished_source_cancels_dispatch as check_unpublish,
)
from tests.test_whatsapp_coexistence import candidate, receive
from tests.test_whatsapp_coexistence import (
    test_echo_cancels_enqueued_delivery as check_echo_delivery,
)
from tests.test_whatsapp_coexistence import (
    test_echo_during_generation_fences_stale_owner as check_echo_generation,
)

URL = os.getenv("BOTWA_TRANSPORT_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


@pytest.fixture
def pg_runtime(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    assert URL
    engine = create_engine(URL)
    try:
        yield Runtime(sessionmaker(bind=engine, autoflush=False), monkeypatch)
    finally:
        engine.dispose()


async def test_postgres_complete_flow(pg_runtime: Runtime) -> None:
    await check_flow(pg_runtime)


async def test_postgres_no_transaction_during_inference(pg_runtime: Runtime) -> None:
    await check_connections(pg_runtime)


async def test_postgres_restart_fencing(pg_runtime: Runtime) -> None:
    await check_restart(pg_runtime)


async def test_postgres_recheck_publication(pg_runtime: Runtime) -> None:
    await check_unpublish(pg_runtime)


async def test_postgres_echo_during_generation(pg_runtime: Runtime) -> None:
    await check_echo_generation(pg_runtime)


async def test_postgres_echo_fences_outbox(
    pg_runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    await check_echo_delivery(pg_runtime, monkeypatch)


def test_postgres_concurrent_echoes_are_recorded_once(pg_runtime: Runtime) -> None:
    barrier = Barrier(2)
    echo = candidate(pg_runtime)

    def accept() -> None:
        barrier.wait(timeout=5)
        asyncio.run(receive(pg_runtime, echo))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(accept) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    with pg_runtime.sessions() as session:
        assert len(session.scalars(select(MessageModel)).all()) == 1
        assert len(session.scalars(select(HandoffSessionModel)).all()) == 1


async def test_postgres_echo_does_not_wait_on_locked_delivery(
    pg_runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.application.whatsapp_live.processor import WhatsAppLiveMessageProcessor
    from app.operations.ai_consumer import dispatch_one

    await pg_runtime.inbound()
    assert await pg_runtime.service.run_once()

    async def defer(*args: object, **kwargs: object) -> bool:
        return False

    with monkeypatch.context() as patch:
        patch.setattr(WhatsAppLiveMessageProcessor, "retry_attempt", defer)
        await dispatch_one(pg_runtime.service)
    with pg_runtime.sessions() as locker:
        locker.scalar(select(OutboundMessageAttemptModel).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run, receive(pg_runtime, candidate(pg_runtime))
            )
            try:
                future.result(timeout=10)
            finally:
                locker.rollback()
    with pg_runtime.sessions() as session:
        job = session.scalars(select(AIJobModel)).one()
        assert job.status == "ready"
        job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert await dispatch_one(pg_runtime.service)
    with pg_runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().status == "cancelled"
        assert (
            session.scalars(select(OutboundMessageAttemptModel)).one().status
            == "failed"
        )


async def test_postgres_concurrent_consumers_claim_once(pg_runtime: Runtime) -> None:
    await pg_runtime.inbound()
    barrier = Barrier(2)

    def claim() -> object:
        barrier.wait(timeout=5)
        return pg_runtime.service.claim()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert sum(result is not None for result in results) == 1
    with pg_runtime.sessions() as session:
        assert session.scalars(select(AIJobModel)).one().attempts == 1
