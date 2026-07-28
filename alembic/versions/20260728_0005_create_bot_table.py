"""create bot table

Revision ID: 20260728_0005
Revises: 20260728_0004
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260728_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="inactive"),
        sa.Column("default_language", sa.String(20), nullable=False, server_default="es"),
        sa.Column(
            "timezone",
            sa.String(100),
            nullable=False,
            server_default="America/Lima",
        ),
        sa.Column("welcome_message", sa.String(1000), nullable=True),
        sa.Column("away_message", sa.String(1000), nullable=True),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_bot_organization_id_organization"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot")),
        sa.UniqueConstraint(
            "organization_id",
            "slug",
            name=op.f("uq_bot_organization_id_slug"),
        ),
    )
    op.create_index(op.f("ix_bot_organization_id"), "bot", ["organization_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_organization_id"), table_name="bot")
    op.drop_table("bot")
