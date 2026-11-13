"""Controlled paraphrase lifecycle on isolated PostgreSQL, with fake providers."""

import pytest
from tests.integration.test_generative_ai_postgresql import URL, pg_runtime
from tests.test_commercial_continuity import (
    test_rejected_draft_keeps_facts_and_skips_recent_question as check_recent,
)
from tests.test_commercial_continuity import (
    test_rejected_literal_without_sources_delivers_continuation_once as check_empty,
)
from tests.test_generative_ai import Runtime
from tests.test_knowledge_paraphrase import (
    test_changed_expression_policy_before_dispatch_cancels as check_revocation,
)
from tests.test_knowledge_paraphrase import (
    test_durable_paraphrase_is_reviewed_and_delivered_once as check_flow,
)
from tests.test_knowledge_paraphrase import (
    test_rejected_paraphrase_asks_pending_question_instead_of_pasting as check_question,
)
from tests.test_knowledge_paraphrase import (
    test_reviewer_rejection_does_not_send_reworded_claim as check_review,
)

__all__ = ["pg_runtime"]
pytestmark = pytest.mark.skipif(not URL, reason="Isolated PostgreSQL URL required")


async def test_postgres_paraphrase_flow(pg_runtime: Runtime) -> None:
    await check_flow(pg_runtime)


async def test_postgres_paraphrase_review(pg_runtime: Runtime) -> None:
    await check_review(pg_runtime)


async def test_postgres_paraphrase_revocation(pg_runtime: Runtime) -> None:
    await check_revocation(pg_runtime)


async def test_postgres_paraphrase_question_fallback(pg_runtime: Runtime) -> None:
    await check_question(pg_runtime)


async def test_postgres_no_dead_end_fallback(pg_runtime: Runtime) -> None:
    await check_empty(pg_runtime)


async def test_postgres_fallback_keeps_facts_and_avoids_recent_question(
    pg_runtime: Runtime,
) -> None:
    await check_recent(pg_runtime)
