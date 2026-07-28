"""create knowledge engine tables

Revision ID: 20260722_0001
Revises: 20260718_0001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260722_0001"
down_revision: str | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_source",
        sa.Column("id", UUID, nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("trust_level", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_source")),
        sa.UniqueConstraint("source_id", name=op.f("uq_knowledge_source_source_id")),
    )
    op.create_table(
        "knowledge_catalog_entry",
        sa.Column("id", UUID, nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("keywords", sa.Text, nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="low"),
        sa.Column("health_score", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_knowledge_catalog_entry"),
        ),
    )
    op.create_table(
        "knowledge_query_log",
        sa.Column("id", UUID, nullable=False),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("intent", sa.String(50), nullable=False),
        sa.Column("response_found", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("response_source", sa.String(100), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_query_log")),
    )


def downgrade() -> None:
    op.drop_table("knowledge_query_log")
    op.drop_table("knowledge_catalog_entry")
    op.drop_table("knowledge_source")
