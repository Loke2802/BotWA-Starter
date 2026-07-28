from pathlib import Path


def test_user_migration_is_reversible_and_linked_to_prd001() -> None:
    migration = Path("alembic/versions/20260728_0003_create_user_table.py").read_text()

    assert 'revision: str = "20260728_0003"' in migration
    assert 'down_revision: str | None = "20260728_0002"' in migration
    assert 'op.create_table(\n        "app_user"' in migration
    assert 'sa.ForeignKeyConstraint(\n            ["organization_id"]' in migration
    assert 'sa.UniqueConstraint("email"' in migration
    assert 'op.drop_table("app_user")' in migration
