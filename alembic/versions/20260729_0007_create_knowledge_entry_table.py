"""create product knowledge entry table

Revision ID: 20260729_0007
Revises: 20260728_0006
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260729_0007"
down_revision: str | None = "20260728_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entry",
        sa.Column("id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("bot_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("updated_by_user_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name=op.f("ck_knowledge_entry_status"),
        ),
        sa.CheckConstraint(
            "source_type = 'manual'",
            name=op.f("ck_knowledge_entry_source_type"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_knowledge_entry_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bot.id"],
            name=op.f("fk_knowledge_entry_bot_id_bot"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_knowledge_entry_created_by_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_knowledge_entry_updated_by_user_id_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_entry")),
    )
    op.create_index(
        op.f("ix_knowledge_entry_organization_id"),
        "knowledge_entry",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_knowledge_entry_bot_id"),
        "knowledge_entry",
        ["bot_id"],
    )
    op.create_index(
        op.f("ix_knowledge_entry_status"),
        "knowledge_entry",
        ["status"],
    )
    op.create_index(
        "ix_knowledge_entry_organization_bot_status",
        "knowledge_entry",
        ["organization_id", "bot_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_entry_organization_bot_status",
        table_name="knowledge_entry",
    )
    op.drop_index(op.f("ix_knowledge_entry_status"), table_name="knowledge_entry")
    op.drop_index(op.f("ix_knowledge_entry_bot_id"), table_name="knowledge_entry")
    op.drop_index(
        op.f("ix_knowledge_entry_organization_id"),
        table_name="knowledge_entry",
    )
    op.drop_table("knowledge_entry")
