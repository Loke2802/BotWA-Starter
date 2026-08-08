import os
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.infrastructure.settings import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url


def _database_url() -> URL:
    return make_url(
        os.getenv(
            "BOTWA_TEST_DATABASE_URL",
            "postgresql+psycopg://botwa:botwa@localhost:5432/postgres",
        )
    )


@pytest.fixture
def migration_database() -> Generator[URL]:
    root_url = _database_url()
    if root_url.get_backend_name() != "postgresql":
        pytest.skip("PRD-010 migration validation requires PostgreSQL")
    database_name = f"botwa_prd010_migration_{uuid4().hex}"
    engine = create_engine(root_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is unavailable: {exc}")
    finally:
        engine.dispose()

    try:
        yield root_url.set(database=database_name)
    finally:
        engine = create_engine(root_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database AND pid <> pg_backend_pid()"
                ),
                {"database": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        engine.dispose()


def _alembic_config(url: URL) -> Config:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    return config


def test_prd_010_migration_chain(migration_database: URL) -> None:
    previous_database_url = os.environ.get("BOTWA_DATABASE_URL")
    os.environ["BOTWA_DATABASE_URL"] = migration_database.render_as_string(
        hide_password=False
    )
    get_settings.cache_clear()
    config = _alembic_config(migration_database)
    try:
        command.upgrade(config, "20260730_0010")
        command.upgrade(config, "20260730_0011")
        command.upgrade(config, "20260730_0012")
        command.downgrade(config, "20260730_0011")
        command.upgrade(config, "20260730_0012")
        command.downgrade(config, "20260730_0010")

        engine = create_engine(migration_database)
        try:
            assert "handoff_session" not in inspect(engine).get_table_names()
            assert "handoff_event" not in inspect(engine).get_table_names()
            assert "conversation" in inspect(engine).get_table_names()

            command.upgrade(config, "head")
            inspector = inspect(engine)
            assert {"handoff_session", "handoff_event"}.issubset(
                inspector.get_table_names()
            )
            assert "uq_handoff_session_conversation" in {
                item["name"]
                for item in inspector.get_unique_constraints("handoff_session")
            }
            assert "uq_outbound_message_attempt_organization_idempotency" in {
                item["name"]
                for item in inspector.get_unique_constraints("outbound_message_attempt")
            }
            assert "ix_handoff_event_session_created" in {
                item["name"] for item in inspector.get_indexes("handoff_event")
            }
            assert "ix_outbound_message_attempt_idempotency_key" in {
                item["name"]
                for item in inspector.get_indexes("outbound_message_attempt")
            }
            assert "contact" in inspector.get_table_names()
            assert "contact_id" in {
                column["name"] for column in inspector.get_columns("conversation")
            }
            command.downgrade(config, "20260730_0012")
            assert "contact" not in inspect(engine).get_table_names()
            command.upgrade(config, "head")
            assert "contact" in inspect(engine).get_table_names()
        finally:
            engine.dispose()
    finally:
        if previous_database_url is None:
            del os.environ["BOTWA_DATABASE_URL"]
        else:
            os.environ["BOTWA_DATABASE_URL"] = previous_database_url
        get_settings.cache_clear()

    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert heads == ["20260808_0016"]
