from pathlib import Path


def test_bot_migration_is_reversible_and_scoped_by_organization() -> None:
    migration = Path("alembic/versions/20260728_0005_create_bot_table.py").read_text()

    assert 'revision: str = "20260728_0005"' in migration
    assert 'down_revision: str | None = "20260728_0004"' in migration
    assert 'op.create_table(\n        "bot"' in migration
    assert '"organization_id"' in migration
    assert '"slug"' in migration
    assert "uq_bot_organization_id_slug" in migration
    assert 'op.drop_table("bot")' in migration
