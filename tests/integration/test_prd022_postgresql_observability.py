import os

import pytest
from app.observability.health import DatabaseReadinessProbe

DATABASE_URL = os.getenv("BOTWA_PRD022_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD022_POSTGRES_URL is required for explicit PostgreSQL tests",
)


def test_prd022_readiness_executes_real_postgresql_select() -> None:
    assert DATABASE_URL is not None
    probe = DatabaseReadinessProbe(DATABASE_URL, timeout_seconds=2.0)
    try:
        assert probe.check().ready
    finally:
        probe.close()
