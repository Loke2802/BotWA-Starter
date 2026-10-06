"""Execute the frozen increment migration against an existing tenant schema."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.infrastructure.database import Base
from sqlalchemy import MetaData, UniqueConstraint, create_engine, inspect, text


def test_upgrade_preserves_existing_data_and_guarded_rollback(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "crm_migration", "alembic/versions/20261006_0027_crm_opportunities.py"
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    existing = MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        if table.name.startswith("crm_"):
            continue
        copied = table.to_metadata(existing)
        for constraint in list(copied.constraints):
            if (
                isinstance(constraint, UniqueConstraint)
                and constraint.name == "uq_conversation_crm_contact"
            ):
                copied.constraints.remove(constraint)
    existing.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organization "
                "(id,name,slug,status,settings,created_at,updated_at) VALUES "
                "('11111111111111111111111111111111','Preserved',"
                "'preserved','active','{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        assert connection.scalar(text("SELECT name FROM organization")) == "Preserved"
        assert "crm_activity" in inspect(connection).get_table_names()
        with Operations.context(context):
            migration.downgrade()
            migration.upgrade()
        connection.execute(
            text(
                "INSERT INTO crm_stage (organization_id,code,name,kind,position) "
                "VALUES ('11111111111111111111111111111111',"
                "'new','Configured','open',0)"
            )
        )
        with (
            Operations.context(context),
            pytest.raises(RuntimeError, match="preserve the schema"),
        ):
            migration.downgrade()
        assert connection.scalar(text("SELECT name FROM crm_stage")) == "Configured"
    engine.dispose()
