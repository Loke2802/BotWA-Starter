"""Opt-in isolated-schema PostgreSQL durability and concurrency checks."""

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from app.application.webchat.service import WebchatService
from app.domain.webchat.contracts import WebchatMessageRequest
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema
from tests.plan_support import allow_all_plan_enforcement
from tests.test_webchat import Runtime, webchat_runtime


@pytest.fixture
def pg_webchat() -> Generator[Runtime]:
    url = os.environ.get("BOTWA_TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("Dedicated PostgreSQL test database not configured")
    # Only this randomly named schema is created/dropped. No existing tables,
    # public schema, production data or user-provided schema names are touched.
    schema = "webchat_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine: Engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with webchat_runtime(engine) as runtime:
            yield runtime
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_postgres_restart_and_concurrent_retry(pg_webchat: Runtime) -> None:
    token = pg_webchat.token()
    barrier = Barrier(2)
    body = WebchatMessageRequest(message="Quiero una web", idempotency_key=uuid4())

    def submit() -> None:
        with Session(pg_webchat.session.get_bind()) as session:
            service = WebchatService(
                session,
                pg_webchat.settings,
                pg_webchat.service.cipher,
                pg_webchat.service.handoff,
                allow_all_plan_enforcement(),
            )
            barrier.wait(timeout=5)
            service.submit(token, "https://kalivur.com", body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    with Session(pg_webchat.session.get_bind()) as restarted:
        assert len(restarted.scalars(select(MessageModel)).all()) == 2
        assert restarted.scalars(select(ConversationModel)).one().message_count == 2
        service = WebchatService(
            restarted,
            pg_webchat.settings,
            pg_webchat.service.cipher,
            pg_webchat.service.handoff,
            allow_all_plan_enforcement(),
        )
        assert len(service.history(token, "https://kalivur.com").messages) == 2
