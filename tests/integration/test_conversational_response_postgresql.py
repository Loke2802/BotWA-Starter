"""Real PostgreSQL durability and reservation locking with synthetic providers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from app.infrastructure.models.ai_generation import AIAttemptModel
from sqlalchemy import select
from tests.integration.test_generative_ai_postgresql import URL, pg_runtime
from tests.test_conversational_response import (
    enable,
)
from tests.test_conversational_response import (
    test_approved_response_is_rechecked_before_send as check_stale,
)
from tests.test_conversational_response import (
    test_complete_response_and_single_outbox as check_flow,
)
from tests.test_conversational_response import (
    test_handoff_during_semantic_review_cancels as check_handoff,
)
from tests.test_conversational_response import (
    test_other_tenant_or_bot_never_enters_response_context as check_scope,
)
from tests.test_conversational_response import (
    test_restart_around_outbox_does_not_duplicate as check_outbox,
)
from tests.test_conversational_response import (
    test_restart_reuses_completed_stages as check_restart,
)
from tests.test_generative_ai import Runtime

__all__ = ["pg_runtime"]
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


async def test_postgres_response_flow(pg_runtime: Runtime) -> None:
    await check_flow(pg_runtime)


@pytest.mark.parametrize("boundary", ["before_outbox", "after_outbox"])
async def test_postgres_outbox_restarts(
    pg_runtime: Runtime, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    await check_outbox(pg_runtime, monkeypatch, boundary)


async def test_postgres_handoff(pg_runtime: Runtime) -> None:
    await check_handoff(pg_runtime)


async def test_postgres_scope(
    pg_runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    await check_scope(pg_runtime, monkeypatch)


@pytest.mark.parametrize(
    "stage",
    [
        "discovery_done",
        "memory_applied",
        "adviser_done",
        "conversational_render_done",
        "semantic_review_done",
    ],
)
async def test_postgres_stage_restarts(
    pg_runtime: Runtime, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    await check_restart(pg_runtime, monkeypatch, stage)


@pytest.mark.parametrize("change", ["memory", "source", "flag", "input"])
async def test_postgres_stale_context(pg_runtime: Runtime, change: str) -> None:
    await check_stale(pg_runtime, change)


async def test_postgres_reservation_is_atomic_and_idempotent(
    pg_runtime: Runtime,
) -> None:
    enable(pg_runtime)
    await pg_runtime.inbound()
    claim = pg_runtime.service.claim()
    assert claim
    barrier = Barrier(2)

    def reserve() -> None:
        barrier.wait(timeout=5)
        pg_runtime.service.reserve_response(*claim)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    with pg_runtime.sessions() as session:
        rows = session.scalars(select(AIAttemptModel)).all()
        assert len(rows) == 2
        assert all(row.result == "reserved" for row in rows)
