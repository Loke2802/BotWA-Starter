"""create business configuration table

Revision ID: 20260728_0006
Revises: 20260728_0005
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260728_0006"
down_revision: str | None = "20260728_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_configuration",
        sa.Column("id", UUID, nullable=False),
        sa.Column("bot_id", UUID, nullable=False),
        sa.Column("business_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column(
            "timezone",
            sa.String(100),
            nullable=False,
            server_default="America/Lima",
        ),
        sa.Column("business_hours", JSONB, nullable=False),
        sa.Column("services", JSONB, nullable=False),
        sa.Column("payment_methods", JSONB, nullable=False),
        sa.Column("policies", JSONB, nullable=False),
        sa.Column("service_instructions", sa.String(4000), nullable=False),
        sa.Column(
            "handoff_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("handoff_message", sa.String(1000), nullable=True),
        sa.Column("handoff_keywords", JSONB, nullable=False),
        sa.Column(
            "handoff_outside_business_hours",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="configured",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bot.id"],
            name=op.f("fk_business_configuration_bot_id_bot"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_configuration")),
        sa.UniqueConstraint("bot_id", name=op.f("uq_business_configuration_bot_id")),
    )
    op.create_index(
        op.f("ix_business_configuration_bot_id"),
        "business_configuration",
        ["bot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_business_configuration_bot_id"),
        table_name="business_configuration",
    )
    op.drop_table("business_configuration")
