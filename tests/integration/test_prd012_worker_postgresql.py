import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.application.automation_management.service import (
    AutomationRetryNotAllowedError,
    ManagedAutomationService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.domain.automation_management.contracts import AutomationDefinitionInput
from app.domain.user.contracts import User
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.managed_automation import ManagedAutomationExecutionModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from tests.plan_support import allow_all_plan_enforcement

DATABASE_URL = os.getenv("BOTWA_PRD012_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="requires real PostgreSQL")


def _service(
    session: Session, *, with_handoff: bool = True
) -> ManagedAutomationService:
    audit_writer = SqlAlchemyAuditRepository(session)
    handoff = (
        HumanHandoffService(
            HumanHandoffRepository(session),
            session,
            audit_writer,
            allow_all_plan_enforcement(),
        )
        if with_handoff
        else None
    )
    return ManagedAutomationService(
        ManagedAutomationRepository(session),
        session,
        audit_writer,
        plan_enforcement=allow_all_plan_enforcement(),
        handoff=handoff,
    )


def _seed(
    factory: sessionmaker[Session], event_count: int = 1
) -> tuple[UUID, UUID, User, list[UUID]]:
    organization_id, bot_id, user_id, conversation_id = (uuid4() for _ in range(4))
    with factory() as session:
        session.add(
            OrganizationModel(
                id=organization_id,
                name="Worker Smoke",
                slug=f"worker-smoke-{organization_id.hex[:10]}",
                status="active",
            )
        )
        session.flush()
        session.add_all(
            [
                BotModel(
                    id=bot_id,
                    organization_id=organization_id,
                    name="Worker Smoke Bot",
                    slug="worker-smoke-bot",
                    status="active",
                ),
                UserModel(
                    id=user_id,
                    organization_id=organization_id,
                    email=f"worker-{user_id}@example.invalid",
                    password_hash="synthetic",
                    role="organization_owner",
                    status="active",
                ),
                ConversationModel(
                    id=conversation_id,
                    company_id=str(organization_id),
                    customer_id="synthetic",
                    organization_id=organization_id,
                    bot_id=bot_id,
                    channel="whatsapp",
                    management_status="open",
                    status="new",
                ),
            ]
        )
        session.commit()
        actor = User(
            id=user_id,
            organization_id=organization_id,
            email=f"worker-{user_id}@example.invalid",
            role="organization_owner",
        )
        service = _service(session)
        definition = service.create(
            organization_id,
            AutomationDefinitionInput(
                name="Worker rule",
                bot_id=str(bot_id),
                trigger_type="conversation.inbound_received",
                conditions_data={
                    "business_hours_state": "outside",
                    "handoff_active": False,
                },
                action_type="request_handoff",
                action_data={"reason_code": "outside_business_hours"},
            ),
            actor,
        )
        service.transition(organization_id, definition.id, "activate", actor)
        for _ in range(event_count):
            service.record_inbound(
                organization_id=organization_id,
                bot_id=bot_id,
                conversation_id=conversation_id,
                contact_id=None,
                channel_type="whatsapp",
                received_at=datetime.now(UTC),
                business_hours_state="outside",
                source_receipt_id=uuid4(),
            )
        execution_ids = list(
            session.scalars(
                select(ManagedAutomationExecutionModel.id).where(
                    ManagedAutomationExecutionModel.automation_definition_id
                    == definition.id
                )
            )
        )
        return organization_id, conversation_id, actor, execution_ids


def _claim(factory: sessionmaker[Session], owner: str, batch_size: int) -> list[UUID]:
    with factory() as session:
        return [
            row.id
            for row in ManagedAutomationRepository(session).claim(owner, batch_size, 60)
        ]


def test_two_workers_do_not_claim_same_execution() -> None:
    assert DATABASE_URL and DATABASE_URL.startswith("postgresql")
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    _, _, _, execution_ids = _seed(factory, event_count=4)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_claim, factory, "worker-a", 2)
        future_b = pool.submit(_claim, factory, "worker-b", 2)
        claimed_a, claimed_b = future_a.result(), future_b.result()
    assert len(claimed_a) == 2
    assert len(claimed_b) == 2
    assert set(claimed_a).isdisjoint(claimed_b)
    assert set(claimed_a + claimed_b) == set(execution_ids)
    with factory() as session:
        rows = list(
            session.scalars(
                select(ManagedAutomationExecutionModel).where(
                    ManagedAutomationExecutionModel.id.in_(execution_ids)
                )
            )
        )
        assert all(row.status == "running" and row.attempt_count == 1 for row in rows)
        assert {row.lease_owner for row in rows} == {"worker-a", "worker-b"}
    engine.dispose()


def test_two_workers_do_not_duplicate_handoff() -> None:
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    _, _, _, execution_ids = _seed(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(lambda owner: _claim(factory, owner, 1), ("worker-a", "worker-b"))
        )
    claimed = [execution_id for group in claims for execution_id in group]
    assert claimed == execution_ids
    with factory() as session:
        row = session.get(ManagedAutomationExecutionModel, claimed[0])
        assert row is not None
        _service(session).run(row)
        assert row.status == "succeeded"
        handoffs = session.scalar(
            select(func.count())
            .select_from(HandoffSessionModel)
            .where(
                HandoffSessionModel.conversation_id
                == row.event_snapshot["conversation_id"]
            )
        )
        assert handoffs == 1
    engine.dispose()


def test_expired_lease_is_recovered() -> None:
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    _, _, _, execution_ids = _seed(factory)
    assert _claim(factory, "worker-a", 1) == execution_ids
    with factory() as session:
        row = session.get(ManagedAutomationExecutionModel, execution_ids[0])
        assert row is not None
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert _claim(factory, "worker-b", 1) == execution_ids
    with factory() as session:
        row = session.get(ManagedAutomationExecutionModel, execution_ids[0])
        assert row is not None
        assert row.lease_owner == "worker-b" and row.attempt_count == 2
        _service(session).run(row)
        assert row.status == "succeeded"
    engine.dispose()


def test_unexpired_lease_is_not_stolen() -> None:
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    _, _, _, execution_ids = _seed(factory)
    assert _claim(factory, "worker-a", 1) == execution_ids
    assert _claim(factory, "worker-b", 1) == []
    with factory() as session:
        row = session.get(ManagedAutomationExecutionModel, execution_ids[0])
        assert row is not None
        assert row.lease_owner == "worker-a" and row.attempt_count == 1
    engine.dispose()


def test_retry_backoff_progression_and_max_attempts() -> None:
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    organization_id, _, actor, execution_ids = _seed(factory)
    execution_id = execution_ids[0]
    snapshots: tuple[dict[str, object], dict[str, object]] | None = None
    for attempt, expected_delay in ((1, 5), (2, 30), (3, None)):
        with factory() as session:
            row = session.get(ManagedAutomationExecutionModel, execution_id)
            assert row is not None
            row.available_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        assert _claim(factory, f"retry-{attempt}", 1) == [execution_id]
        with factory() as session:
            row = session.get(ManagedAutomationExecutionModel, execution_id)
            assert row is not None
            if snapshots is None:
                snapshots = (dict(row.definition_snapshot), dict(row.event_snapshot))
            before = datetime.now(UTC)
            _service(session, with_handoff=False).run(row)
            assert row.attempt_count == attempt
            assert row.safe_error_code == "INTERNAL_ERROR"
            if expected_delay is None:
                assert row.status == "failed" and row.completed_at is not None
            else:
                assert row.status == "pending"
                assert (
                    before + timedelta(seconds=expected_delay - 1) <= row.available_at
                )
                assert row.available_at <= before + timedelta(
                    seconds=expected_delay + 1
                )
    assert _claim(factory, "retry-4", 1) == []
    with factory() as session:
        service = _service(session)
        with pytest.raises(AutomationRetryNotAllowedError):
            service.retry_execution(organization_id, execution_id, actor)
        row = session.get(ManagedAutomationExecutionModel, execution_id)
        assert row is not None and snapshots is not None
        assert row.definition_snapshot == snapshots[0]
        assert row.event_snapshot == snapshots[1]
    engine.dispose()


def test_manual_retry_reuses_execution_and_terminal_error_is_safe() -> None:
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    organization_id, _, actor, execution_ids = _seed(factory, event_count=2)
    retry_id, terminal_id = execution_ids
    with factory() as session:
        retry_row = session.get(ManagedAutomationExecutionModel, retry_id)
        terminal_row = session.get(ManagedAutomationExecutionModel, terminal_id)
        assert retry_row is not None and terminal_row is not None
        retry_row.status = "failed"
        retry_row.attempt_count = 2
        retry_row.safe_error_code = "INTERNAL_ERROR"
        terminal_row.definition_snapshot = {}
        session.commit()
        before_count = session.scalar(
            select(func.count()).select_from(ManagedAutomationExecutionModel)
        )
        retried = _service(session).retry_execution(organization_id, retry_id, actor)
        assert retried.id == retry_id and retried.status == "pending"
        assert retried.attempt_count == 2 and retried.safe_error_code is None
        retried.available_at = datetime.now(UTC) + timedelta(minutes=5)
        session.commit()
        assert (
            session.scalar(
                select(func.count()).select_from(ManagedAutomationExecutionModel)
            )
            == before_count
        )
    assert _claim(factory, "terminal-worker", 1) == [terminal_id]
    with factory() as session:
        terminal = session.get(ManagedAutomationExecutionModel, terminal_id)
        assert terminal is not None
        _service(session).run(terminal)
        assert terminal.status == "failed"
        assert terminal.safe_error_code == "INVALID_SNAPSHOT"
        assert terminal.completed_at is not None
        assert terminal.lease_owner is None and terminal.lease_expires_at is None
    engine.dispose()
