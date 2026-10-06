"""Real PostgreSQL: duplicate requests, competing edits and tenant constraints."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from app.domain.crm.contracts import CrmConflict, OpportunityCreate, OpportunityUpdate
from app.infrastructure.models.crm_opportunity import (
    OpportunityConversationModel,
    OpportunityModel,
)
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.crm_opportunity_support import opportunity_service, payload, seed

DATABASE_URL = os.getenv("BOTWA_CRM_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="Explicit CRM PostgreSQL test URL required"
)


@pytest.fixture
def database():  # type: ignore[no-untyped-def]
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    with Session(engine) as session:
        actor, other, contact, conversation = seed(session)
    try:
        yield engine, actor, other, contact, conversation
    finally:
        # Only synthetic tenant records created by this fixture.
        with engine.begin() as connection:
            for org in [actor.organization_id, other.organization_id]:
                for table in (
                    "crm_opportunity_history",
                    "crm_opportunity_conversation",
                    "crm_activity",
                    "crm_opportunity",
                    "crm_stage",
                    "audit_event",
                    "conversation",
                    "customer_profile",
                    "contact",
                    "bot",
                    "app_user",
                ):
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE organization_id = :org"),
                        {"org": org},
                    )
                connection.execute(
                    text("DELETE FROM organization WHERE id = :org"), {"org": org}
                )
        engine.dispose()


def test_simultaneous_creation_same_key_is_one_opportunity(database):  # type: ignore[no-untyped-def]
    engine, actor, _, contact, conversation = database
    data = OpportunityCreate.model_validate(payload(actor, contact, conversation))
    barrier = Barrier(2)

    def create(_: int) -> UUID:
        with Session(engine) as session:
            barrier.wait(timeout=15)
            return (
                opportunity_service(session)
                .create(actor.organization_id, actor, data, "race-key")
                .id
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(create, [1, 2]))
    assert ids[0] == ids[1]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(OpportunityModel)
                .where(OpportunityModel.organization_id == actor.organization_id)
            )
            == 1
        )
        for table in (
            "crm_activity",
            "crm_opportunity_history",
            "crm_opportunity_conversation",
        ):
            assert (
                session.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE organization_id = :org"),
                    {"org": actor.organization_id},
                )
                == 1
            )


def test_competing_updates_preserve_first_writer(database):  # type: ignore[no-untyped-def]
    engine, actor, _, contact, conversation = database
    data = OpportunityCreate.model_validate(payload(actor, contact, conversation))
    with Session(engine) as session:
        created = opportunity_service(session).create(
            actor.organization_id, actor, data, "edit-race"
        )
    barrier = Barrier(2)

    def edit(title: str) -> str:
        with Session(engine) as session:
            barrier.wait(timeout=15)
            update = OpportunityUpdate.model_validate(
                {
                    **data.model_dump(exclude={"contact_id", "conversation_id"}),
                    "title": title,
                    "version": 1,
                }
            )
            try:
                opportunity_service(session).update(
                    actor.organization_id, created.id, actor, update
                )
                return "saved"
            except CrmConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["First writer", "Second writer"]))
    assert sorted(results) == ["conflict", "saved"]
    with Session(engine) as session:
        service = opportunity_service(session)
        assert service.get(actor.organization_id, created.id, actor).version == 2
        assert (
            len(service.history(actor.organization_id, created.id, actor, 1, 20)) == 2
        )


def test_postgresql_rejects_cross_tenant_assignee_and_link(database):  # type: ignore[no-untyped-def]
    engine, actor, other, contact, conversation = database
    with Session(engine) as session:
        item = opportunity_service(session).create(
            actor.organization_id,
            actor,
            OpportunityCreate.model_validate(payload(actor, contact, conversation)),
            "fk-test",
        )
        row = session.get(OpportunityModel, item.id)
        assert row is not None
        row.assigned_user_id = other.id
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        link = session.get(OpportunityConversationModel, (item.id, conversation))
        assert link is not None
        link.organization_id = other.organization_id
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
