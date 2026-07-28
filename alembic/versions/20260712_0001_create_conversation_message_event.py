"""create conversation message event tables

Revision ID: 20260712_0001
Revises: 20260710_0001
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260712_0001"
down_revision: str | None = "20260710_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", UUID, nullable=False),
        sa.Column("company_id", sa.String(255), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column("business_case_id", UUID, nullable=True),
        sa.Column("channel", sa.String(50), nullable=False, server_default="http"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("external_conversation_id", sa.String(255), nullable=True),
        sa.Column("extra_data", JSONB, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation")),
    )
    op.create_table(
        "message",
        sa.Column("id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("extra_data", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_message_conversation_id_conversation"),
        ),
    )
    op.create_table(
        "business_event",
        sa.Column("id", UUID, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("conversation_id", UUID, nullable=True),
        sa.Column("business_case_id", UUID, nullable=True),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_event")),
    )
    op.create_index(
        op.f("ix_business_event_event_type"),
        "business_event",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_business_event_event_type"), table_name="business_event")
    op.drop_table("business_event")
    op.drop_table("message")
    op.drop_table("conversation")
