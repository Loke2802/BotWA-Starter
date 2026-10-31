"""Run the erasure contract on an explicitly isolated, migrated PostgreSQL DB."""

import os
from collections.abc import Generator

import pytest
from app.infrastructure.database import Base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from tests.test_privacy_erasure import (
    test_active_ai_is_never_deleted,
    test_activity_boundary,
    test_ambiguous_receipt_and_scope_fail_closed,
    test_history_handoff_transport_and_checkpoints_are_removed,
    test_internal_timestamp_is_a_separate_safety_block,
    test_legacy_unattributed_data_blocks,
    test_maintenance_lock_excludes_writers_and_other_erasers,
    test_other_tenant_legacy_event_blocks_without_erasing_it,
    test_preview_apply_idempotency_and_isolation,
    test_reactivation_invalidates_preview_and_request_bypasses_age,
    test_reverse_link_and_rollback,
    test_row_limit_and_fresh_session,
    test_shared_contact_and_reverse_transport_block,
)

URL = os.getenv("BOTWA_TRANSPORT_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Explicit isolated PostgreSQL URL required"
)


@pytest.fixture
def privacy_sessions() -> Generator[sessionmaker[Session]]:
    assert URL
    engine = create_engine(URL)
    with engine.begin() as connection:
        names = ", ".join('"' + name + '"' for name in sorted(Base.metadata.tables))
        connection.execute(text(f"TRUNCATE TABLE {names} CASCADE"))
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


__all__ = [
    "test_internal_timestamp_is_a_separate_safety_block",
    "test_other_tenant_legacy_event_blocks_without_erasing_it",
    "test_activity_boundary",
    "test_reverse_link_and_rollback",
    "test_legacy_unattributed_data_blocks",
    "test_active_ai_is_never_deleted",
    "test_maintenance_lock_excludes_writers_and_other_erasers",
    "test_shared_contact_and_reverse_transport_block",
    "test_history_handoff_transport_and_checkpoints_are_removed",
    "test_ambiguous_receipt_and_scope_fail_closed",
    "test_preview_apply_idempotency_and_isolation",
    "test_reactivation_invalidates_preview_and_request_bypasses_age",
    "test_row_limit_and_fresh_session",
]
