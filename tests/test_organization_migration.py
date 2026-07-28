from pathlib import Path


def test_organization_migration_is_reversible() -> None:
    migration = Path(
        "alembic/versions/20260728_0002_create_organization_table.py"
    ).read_text()

    assert 'revision: str = "20260728_0002"' in migration
    assert 'down_revision: str | None = "20260728_0001"' in migration
    assert 'op.create_table(\n        "organization"' in migration
    assert 'sa.UniqueConstraint("slug"' in migration
    assert 'op.drop_table("organization")' in migration
