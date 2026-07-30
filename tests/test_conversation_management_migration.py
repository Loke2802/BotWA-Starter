from pathlib import Path


def test_conversation_management_migration_extends_existing_tables_safely() -> None:
    migration_path = Path(
        "alembic/versions/20260730_0010_create_conversation_management_tables.py"
    )
    migration = migration_path.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260730_0009"' in migration
    assert 'op.add_column("conversation"' in migration
    assert 'op.add_column("message"' in migration
    assert "uq_conversation_managed_identity" in migration
    assert "uq_message_inbound_external" in migration
    assert "uq_message_outbound_attempt" in migration
    assert "conversation_management_status" in migration
    assert "message_management_direction" in migration
