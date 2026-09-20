"""Real PG leases, transactions and idempotency; external providers stay fake."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from app.infrastructure.models.ai_generation import AIJobModel
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
