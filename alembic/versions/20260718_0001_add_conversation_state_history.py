"""add conversation_state_history table

Revision ID: 20260718_0001
Revises: 20260712_0001
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260718_0001"
down_revision: str | None = "20260712_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_state_history",
        sa.Column("id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("from_state", sa.String(50), nullable=False),
        sa.Column("to_state", sa.String(50), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_state_history")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_conversation_state_history_conversation_id_conversation"),
        ),
    )


def downgrade() -> None:
    op.drop_table("conversation_state_history")
