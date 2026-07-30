from pathlib import Path

MIGRATION = Path(
    "alembic/versions/20260729_0007_create_knowledge_entry_table.py",
)


def test_knowledge_entry_migration_declares_expected_schema() -> None:
    content = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "20260729_0007"' in content
    assert 'down_revision: str | None = "20260728_0006"' in content
    assert '"knowledge_entry"' in content
    assert "fk_knowledge_entry_organization_id_organization" in content
    assert "fk_knowledge_entry_bot_id_bot" in content
    assert "ix_knowledge_entry_organization_bot_status" in content
    assert "ck_knowledge_entry_status" in content
    assert 'op.drop_table("knowledge_entry")' in content
