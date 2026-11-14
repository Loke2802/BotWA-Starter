"""Run IA memory retention and fencing checks against isolated PostgreSQL."""

import os

import pytest
from tests.test_ai_memory_retention import (
    test_active_job_blocks_supervised_sweep as check_active,
)
from tests.test_ai_memory_retention import (
    test_expired_memory_and_old_history_are_not_sent_to_model as check_expiry,
)
from tests.test_generative_ai import Runtime

pytest_plugins = ("tests.integration.test_generative_ai_postgresql",)

pytestmark = pytest.mark.skipif(
    not os.getenv("BOTWA_TRANSPORT_POSTGRES_URL"),
    reason="Isolated PostgreSQL URL required",
)


async def test_postgresql_expired_memory_is_not_sent(pg_runtime: Runtime) -> None:
    await check_expiry(pg_runtime)


async def test_postgresql_active_job_blocks_sweep(pg_runtime: Runtime) -> None:
    await check_active(pg_runtime)
