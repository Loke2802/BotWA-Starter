from pathlib import Path


def test_whatsapp_configuration_migration_is_linear_and_indexed() -> None:
    source = Path(
        "alembic/versions/"
        "20260730_0008_create_whatsapp_channel_configuration_table.py",
    ).read_text(encoding="utf-8")

    assert 'revision: str = "20260730_0008"' in source
    assert 'down_revision: str | None = "20260729_0007"' in source
    assert '"whatsapp_channel_configuration"' in source
    assert "phone_number_id" in source
    assert "public_webhook_id" in source
    assert "verify_token_ciphertext" in source
    assert "app_secret_ciphertext" in source
    assert "ix_whatsapp_channel_configuration_organization_bot_status" in source
    assert "sa.UniqueConstraint" in source
