from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    inspect,
    select,
)
from sqlalchemy.exc import IntegrityError

from tests.sqlite_schema_support import SqliteSchemaTemplates


def schema() -> tuple[MetaData, Table, Table]:
    metadata = MetaData()
    parent = Table(
        "parent",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String, unique=True),
    )
    child = Table(
        "child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parent.id")),
    )
    return metadata, parent, child


def test_copies_isolate_data_keep_constraints_and_persist_after_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata, parent, child = schema()
    original = metadata.create_all
    builds: list[Engine] = []

    def observed(engine: Engine) -> None:
        builds.append(engine)
        original(engine)

    monkeypatch.setattr(metadata, "create_all", observed)
    templates = SqliteSchemaTemplates(tmp_path / "templates", metadata)
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    templates.prepare(first)
    templates.prepare(second)
    assert len(builds) == 1
    engine = create_engine(f"sqlite:///{first}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.execute(parent.insert().values(id=1, name="First"))
        connection.execute(child.insert().values(id=1, parent_id=1))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(parent.insert().values(id=2, name="First"))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(child.insert().values(id=2, parent_id=999))
    engine.dispose()
    reopened = create_engine(f"sqlite:///{first}")
    isolated = create_engine(f"sqlite:///{second}")
    try:
        with reopened.connect() as connection:
            assert connection.scalars(select(parent.c.name)).all() == ["First"]
            assert connection.scalars(select(child.c.parent_id)).all() == [1]
        with isolated.begin() as connection:
            assert connection.execute(select(parent)).all() == []
            assert connection.execute(select(child)).all() == []
            connection.execute(parent.insert().values(id=1, name="Second"))
    finally:
        reopened.dispose()
        isolated.dispose()


def test_schema_and_index_changes_get_fresh_empty_template(tmp_path: Path) -> None:
    metadata, parent, _ = schema()
    templates = SqliteSchemaTemplates(tmp_path / "templates", metadata)
    first, second = tmp_path / "before.sqlite", tmp_path / "after.sqlite"
    templates.prepare(first)
    Table("added", metadata, Column("id", Integer, primary_key=True))
    Index("ix_parent_name", parent.c.name)
    templates.prepare(second)
    before, after = create_engine(f"sqlite:///{first}"), create_engine(
        f"sqlite:///{second}"
    )
    try:
        assert "added" not in inspect(before).get_table_names()
        assert "added" in inspect(after).get_table_names()
        assert not inspect(before).get_indexes("parent")
        assert inspect(after).get_indexes("parent")[0]["name"] == "ix_parent_name"
    finally:
        before.dispose()
        after.dispose()


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    metadata, _, _ = schema()
    destination = tmp_path / "retained.sqlite"
    destination.write_bytes(b"retained evidence")
    templates = SqliteSchemaTemplates(tmp_path / "templates", metadata)
    with pytest.raises(FileExistsError):
        templates.prepare(destination)
    assert destination.read_bytes() == b"retained evidence"


def test_seeded_schema_is_rejected_instead_of_sharing_test_data(tmp_path: Path) -> None:
    metadata, parent, _ = schema()

    @event.listens_for(metadata, "after_create")
    def seed(_, connection, **kwargs):  # type: ignore[no-untyped-def]
        connection.execute(parent.insert().values(id=1, name="Leaked seed"))

    templates = SqliteSchemaTemplates(tmp_path / "templates", metadata)
    destination = tmp_path / "fresh.sqlite"
    with pytest.raises(ValueError, match="must contain no rows"):
        templates.prepare(destination)
    assert not destination.exists()
