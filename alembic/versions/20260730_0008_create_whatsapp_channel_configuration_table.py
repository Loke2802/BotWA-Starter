"""create WhatsApp channel configuration table

Revision ID: 20260730_0008
Revises: 20260729_0007
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260730_0008"
down_revision: str | None = "20260729_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_channel_configuration",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("bot_id", UUID, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("phone_number_id", sa.String(100), nullable=False),
        sa.Column("whatsapp_business_account_id", sa.String(100), nullable=False),
        sa.Column("public_webhook_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "webhook_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("verify_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("app_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'inactive')",
            name=op.f("ck_whatsapp_channel_configuration_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f(
                "fk_whatsapp_channel_configuration_organization_id_organization",
            ),
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bot.id"],
            name=op.f("fk_whatsapp_channel_configuration_bot_id_bot"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app_user.id"],
            name=op.f(
                "fk_whatsapp_channel_configuration_created_by_user_id_app_user",
            ),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["app_user.id"],
            name=op.f(
                "fk_whatsapp_channel_configuration_updated_by_user_id_app_user",
            ),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_whatsapp_channel_configuration"),
        ),
        sa.UniqueConstraint(
            "phone_number_id",
            name=op.f("uq_whatsapp_channel_configuration_phone_number_id"),
        ),
        sa.UniqueConstraint(
            "public_webhook_id",
            name=op.f("uq_whatsapp_channel_configuration_public_webhook_id"),
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_channel_configuration_organization_id"),
        "whatsapp_channel_configuration",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_whatsapp_channel_configuration_bot_id"),
        "whatsapp_channel_configuration",
        ["bot_id"],
    )
    op.create_index(
        op.f("ix_whatsapp_channel_configuration_status"),
        "whatsapp_channel_configuration",
        ["status"],
    )
    op.create_index(
        op.f("ix_whatsapp_channel_configuration_whatsapp_business_account_id"),
        "whatsapp_channel_configuration",
        ["whatsapp_business_account_id"],
    )
    op.create_index(
        "ix_whatsapp_channel_configuration_organization_bot_status",
        "whatsapp_channel_configuration",
        ["organization_id", "bot_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whatsapp_channel_configuration_organization_bot_status",
        table_name="whatsapp_channel_configuration",
    )
    op.drop_index(
        op.f("ix_whatsapp_channel_configuration_whatsapp_business_account_id"),
        table_name="whatsapp_channel_configuration",
    )
    op.drop_index(
        op.f("ix_whatsapp_channel_configuration_status"),
        table_name="whatsapp_channel_configuration",
    )
    op.drop_index(
        op.f("ix_whatsapp_channel_configuration_bot_id"),
        table_name="whatsapp_channel_configuration",
    )
    op.drop_index(
        op.f("ix_whatsapp_channel_configuration_organization_id"),
        table_name="whatsapp_channel_configuration",
    )
    op.drop_table("whatsapp_channel_configuration")
