from pathlib import Path

MIGRATION = Path(
    "alembic/versions/20260728_0006_create_business_configuration_table.py",
)


def test_business_configuration_migration_declares_expected_revision() -> None:
    content = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260728_0006"' in content
    assert 'down_revision: str | None = "20260728_0005"' in content
    assert '"business_configuration"' in content
    assert '"bot_id"' in content
    assert "uq_business_configuration_bot_id" in content
    assert "fk_business_configuration_bot_id_bot" in content
    assert "ix_business_configuration_bot_id" in content
    assert 'op.drop_table("business_configuration")' in content
