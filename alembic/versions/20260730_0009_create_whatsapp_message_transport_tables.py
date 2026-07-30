"""create WhatsApp message transport tables

Revision ID: 20260730_0009
Revises: 20260730_0008
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260730_0009"
down_revision: str | None = "20260730_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_message_receipt",
        sa.Column("id", UUID, nullable=False),
        sa.Column("channel_type", sa.String(30), nullable=False),
        sa.Column("external_message_id", sa.String(255), nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("bot_id", UUID, nullable=False),
        sa.Column("channel_configuration_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'failed')",
            name=op.f("ck_inbound_message_receipt_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_inbound_message_receipt_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bot.id"],
            name=op.f("fk_inbound_message_receipt_bot_id_bot"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_configuration_id"],
            ["whatsapp_channel_configuration.id"],
            name=op.f(
                "fk_inbound_message_receipt_channel_configuration_id_"
                "whatsapp_channel_configuration"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_message_receipt")),
        sa.UniqueConstraint(
            "channel_type",
            "external_message_id",
            name="uq_inbound_message_receipt_channel_message",
        ),
    )
    op.create_index(
        op.f("ix_inbound_message_receipt_organization_id"),
        "inbound_message_receipt",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_inbound_message_receipt_bot_id"),
        "inbound_message_receipt",
        ["bot_id"],
    )
    op.create_index(
        op.f("ix_inbound_message_receipt_channel_configuration_id"),
        "inbound_message_receipt",
        ["channel_configuration_id"],
    )
    op.create_index(
        op.f("ix_inbound_message_receipt_status"),
        "inbound_message_receipt",
        ["status"],
    )
    op.create_index(
        "ix_inbound_message_receipt_organization_bot_status",
        "inbound_message_receipt",
        ["organization_id", "bot_id", "status"],
    )

    op.create_table(
        "outbound_message_attempt",
        sa.Column("id", UUID, nullable=False),
        sa.Column("inbound_receipt_id", UUID, nullable=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("bot_id", UUID, nullable=False),
        sa.Column("channel_configuration_id", UUID, nullable=False),
        sa.Column("external_recipient_hash", sa.String(64), nullable=False),
        sa.Column("external_recipient_ciphertext", sa.Text(), nullable=False),
        sa.Column("message_ciphertext", sa.Text(), nullable=False),
        sa.Column("reply_to_external_message_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provider_status_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'delivered', 'read', 'failed')",
            name=op.f("ck_outbound_message_attempt_status"),
        ),
        sa.ForeignKeyConstraint(
            ["inbound_receipt_id"],
            ["inbound_message_receipt.id"],
            name=op.f(
                "fk_outbound_message_attempt_inbound_receipt_id_"
                "inbound_message_receipt"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_outbound_message_attempt_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bot.id"],
            name=op.f("fk_outbound_message_attempt_bot_id_bot"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_configuration_id"],
            ["whatsapp_channel_configuration.id"],
            name=op.f(
                "fk_outbound_message_attempt_channel_configuration_id_"
                "whatsapp_channel_configuration"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_message_attempt")),
        sa.UniqueConstraint(
            "provider_message_id",
            name=op.f("uq_outbound_message_attempt_provider_message_id"),
        ),
    )
    op.create_index(
        op.f("ix_outbound_message_attempt_inbound_receipt_id"),
        "outbound_message_attempt",
        ["inbound_receipt_id"],
    )
    op.create_index(
        op.f("ix_outbound_message_attempt_organization_id"),
        "outbound_message_attempt",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_outbound_message_attempt_bot_id"),
        "outbound_message_attempt",
        ["bot_id"],
    )
    op.create_index(
        op.f("ix_outbound_message_attempt_channel_configuration_id"),
        "outbound_message_attempt",
        ["channel_configuration_id"],
    )
    op.create_index(
        op.f("ix_outbound_message_attempt_status"),
        "outbound_message_attempt",
        ["status"],
    )
    op.create_index(
        op.f("ix_outbound_message_attempt_provider_message_id"),
        "outbound_message_attempt",
        ["provider_message_id"],
    )
    op.create_index(
        "ix_outbound_message_attempt_organization_bot_status",
        "outbound_message_attempt",
        ["organization_id", "bot_id", "status"],
    )
    op.create_index(
        "ix_outbound_message_attempt_status_next_attempt",
        "outbound_message_attempt",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbound_message_attempt_status_next_attempt",
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        "ix_outbound_message_attempt_organization_bot_status",
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        op.f("ix_outbound_message_attempt_provider_message_id"),
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        op.f("ix_outbound_message_attempt_status"),
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        op.f("ix_outbound_message_attempt_channel_configuration_id"),
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        op.f("ix_outbound_message_attempt_bot_id"),
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        op.f("ix_outbound_message_attempt_organization_id"),
        table_name="outbound_message_attempt",
    )
    op.drop_index(
        op.f("ix_outbound_message_attempt_inbound_receipt_id"),
        table_name="outbound_message_attempt",
    )
    op.drop_table("outbound_message_attempt")

    op.drop_index(
        "ix_inbound_message_receipt_organization_bot_status",
        table_name="inbound_message_receipt",
    )
    op.drop_index(
        op.f("ix_inbound_message_receipt_status"),
        table_name="inbound_message_receipt",
    )
    op.drop_index(
        op.f("ix_inbound_message_receipt_channel_configuration_id"),
        table_name="inbound_message_receipt",
    )
    op.drop_index(
        op.f("ix_inbound_message_receipt_bot_id"),
        table_name="inbound_message_receipt",
    )
    op.drop_index(
        op.f("ix_inbound_message_receipt_organization_id"),
        table_name="inbound_message_receipt",
    )
    op.drop_table("inbound_message_receipt")
