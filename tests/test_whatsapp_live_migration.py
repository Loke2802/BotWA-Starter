from pathlib import Path


def test_whatsapp_live_migration_is_linear_constrained_and_indexed() -> None:
    source = Path(
        "alembic/versions/" "20260730_0009_create_whatsapp_message_transport_tables.py",
    ).read_text(encoding="utf-8")

    assert 'revision: str = "20260730_0009"' in source
    assert 'down_revision: str | None = "20260730_0008"' in source
    assert '"inbound_message_receipt"' in source
    assert '"outbound_message_attempt"' in source
    assert "uq_inbound_message_receipt_channel_message" in source
    assert "uq_outbound_message_attempt_provider_message_id" in source
    assert "external_recipient_ciphertext" in source
    assert "message_ciphertext" in source
    assert "ix_inbound_message_receipt_organization_bot_status" in source
    assert "ix_outbound_message_attempt_status_next_attempt" in source
    assert "sa.CheckConstraint" in source
