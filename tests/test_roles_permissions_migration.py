from pathlib import Path


def test_roles_migration_is_reversible_and_backfills_users() -> None:
    migration = Path("alembic/versions/20260728_0004_add_user_roles.py").read_text()

    assert 'revision: str = "20260728_0004"' in migration
    assert 'down_revision: str | None = "20260728_0003"' in migration
    assert '"role"' in migration
    assert "organization_owner" in migration
    assert "ROW_NUMBER()" in migration
    assert 'op.drop_column("app_user", "role")' in migration
