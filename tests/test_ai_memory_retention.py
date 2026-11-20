"""Expiration must be tenant-scoped and must not resurrect stale context."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.generative_ai.memory_retention import inspect_memory_retention
from app.infrastructure.models.ai_generation import AIJobModel, AIMemoryModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from sqlalchemy import select

from tests.test_generative_ai import Runtime
from tests.test_luri_stabilization import seed_channel
from tests.test_whatsapp_live_processor_repository import cipher

pytest_plugins = ("tests.test_generative_ai",)


def test_supervised_sweep_is_read_only_by_default_and_scoped(runtime: Runtime) -> None:
    old = datetime.now(UTC) - timedelta(days=31)
    with runtime.sessions() as session:
        other = seed_channel(session, str(int(uuid4()) % 10**12))
        own_conversation = ConversationModel(
            company_id=str(runtime.channel.organization_id),
            customer_id="own",
            organization_id=runtime.channel.organization_id,
            bot_id=runtime.channel.bot_id,
        )
        other_conversation = ConversationModel(
            company_id=str(other.organization_id),
            customer_id="other",
            organization_id=other.organization_id,
            bot_id=other.bot_id,
        )
        legacy_conversation = ConversationModel(
            company_id=str(runtime.channel.organization_id),
            customer_id="legacy",
            organization_id=runtime.channel.organization_id,
            bot_id=runtime.channel.bot_id,
        )
        session.add_all([own_conversation, other_conversation, legacy_conversation])
        session.flush()
        session.add_all(
            [
                AIMemoryModel(
                    conversation_id=own_conversation.id,
                    organization_id=runtime.channel.organization_id,
                    bot_id=runtime.channel.bot_id,
                    revision=1,
                    ciphertext=cipher().encrypt('{"secret":"own"}'),
                    updated_at=old,
                ),
                AIMemoryModel(
                    conversation_id=other_conversation.id,
                    organization_id=other.organization_id,
                    bot_id=other.bot_id,
                    revision=1,
                    ciphertext=cipher().encrypt('{"secret":"other"}'),
                    updated_at=old,
                ),
                AIMemoryModel(
                    conversation_id=legacy_conversation.id,
                    organization_id=runtime.channel.organization_id,
                    bot_id=runtime.channel.bot_id,
                    revision=1,
                    ciphertext=cipher().encrypt('{"secret":"unknown-age"}'),
                    updated_at=None,
                ),
            ]
        )
        session.commit()
        own_id, other_id, legacy_id = (
            own_conversation.id,
            other_conversation.id,
            legacy_conversation.id,
        )

    with runtime.sessions() as session:
        preview = inspect_memory_retention(
            session, runtime.channel.organization_id, runtime.channel.bot_id
        )
        assert (preview.eligible, preview.cleared) == (2, 0)
        session.commit()
    with runtime.sessions() as session:
        assert session.get(AIMemoryModel, own_id) is not None
        applied = inspect_memory_retention(
            session,
            runtime.channel.organization_id,
            runtime.channel.bot_id,
            apply=True,
        )
        assert (applied.eligible, applied.cleared) == (2, 2)
        session.commit()
    with runtime.sessions() as session:
        assert session.get(AIMemoryModel, own_id) is None
        assert session.get(AIMemoryModel, legacy_id) is None
        assert session.get(AIMemoryModel, other_id) is not None
        again = inspect_memory_retention(
            session,
            runtime.channel.organization_id,
            runtime.channel.bot_id,
            apply=True,
        )
        assert again.cleared == 0


async def test_expired_memory_and_old_history_are_not_sent_to_model(
    runtime: Runtime,
) -> None:
    await runtime.inbound(f"privacy-old-{uuid4()}")
    old = datetime.now(UTC) - timedelta(days=31)
    with runtime.sessions() as session:
        first = session.scalars(
            select(AIJobModel).where(
                AIJobModel.organization_id == runtime.channel.organization_id,
                AIJobModel.bot_id == runtime.channel.bot_id,
            )
        ).one()
        session.add(
            AIMemoryModel(
                conversation_id=first.conversation_id,
                organization_id=first.organization_id,
                bot_id=first.bot_id,
                revision=1,
                ciphertext=cipher().encrypt('{"secret":"old"}'),
                updated_at=old,
            )
        )
        conversation_id = first.conversation_id
        first.status = "sent"
        first.created_at = old
        for row in session.scalars(select(MessageModel)).all():
            row.occurred_at = old
        session.commit()
    await runtime.inbound(f"privacy-new-{uuid4()}")
    with runtime.sessions() as session:
        current = session.scalars(
            select(AIJobModel).where(
                AIJobModel.organization_id == runtime.channel.organization_id,
                AIJobModel.bot_id == runtime.channel.bot_id,
                AIJobModel.status == "pending",
            )
        ).one()
        current.status = "running"
        current.token = uuid4()
        current.lease_until = datetime.now(UTC) + timedelta(minutes=2)
        current_id, token = current.id, current.token
        session.commit()
    assert token is not None
    snapshot = runtime.service.snapshot(current_id, token)
    assert snapshot["memory"] == {}
    assert len(snapshot["history"]) == 1
    with runtime.sessions() as session:
        memory = session.get(AIMemoryModel, conversation_id)
        assert memory is not None
        assert json.loads(cipher().decrypt(memory.ciphertext)) == {}
        assert memory.revision == 2
        assert memory.updated_at is not None


async def test_active_job_blocks_supervised_sweep(runtime: Runtime) -> None:
    await runtime.inbound(f"privacy-active-{uuid4()}")
    with runtime.sessions() as session:
        job = session.scalars(
            select(AIJobModel).where(
                AIJobModel.organization_id == runtime.channel.organization_id,
                AIJobModel.bot_id == runtime.channel.bot_id,
            )
        ).one()
        conversation_id = job.conversation_id
        session.add(
            AIMemoryModel(
                conversation_id=job.conversation_id,
                organization_id=job.organization_id,
                bot_id=job.bot_id,
                revision=1,
                ciphertext=cipher().encrypt('{"secret":"waiting"}'),
                updated_at=datetime.now(UTC) - timedelta(days=31),
            )
        )
        session.commit()
    with runtime.sessions() as session:
        result = inspect_memory_retention(
            session,
            runtime.channel.organization_id,
            runtime.channel.bot_id,
            apply=True,
        )
        assert (result.eligible, result.cleared, result.skipped_active) == (1, 0, 1)
        session.commit()
    with runtime.sessions() as session:
        assert session.get(AIMemoryModel, conversation_id) is not None
